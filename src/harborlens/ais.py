"""NOAA-style historical AIS processing with unvalidated stationary candidates.

Experimental research only. Do NOT use for navigation, vessel control,
live traffic management, port-call truth, or certified emissions estimates.
"""
from __future__ import annotations
import csv
import errno
import gzip
import hashlib
import io
import itertools
import json
import math
import os
import stat
import tempfile
import zipfile
from pathlib import Path
from harborlens.cli_usage import escape_error_text
from harborlens.csv_safe import CsvDictWriter, neutralize_text_cell, recover_text_cell
from harborlens.io_safe import stream_rows, AISInputError
from harborlens.timeparse import parse_observation_time
from harborlens.provenance import add_provenance, require_declared_source_url
from harborlens.censoring import (
    WindowCensoring, declaration_record, declared_window, observed_range, parse_utc,
    resolve_input_window,
)
from harborlens.vessel import csv_value, mmsi_category, normalize_attributes, parse_csv_attributes
from harborlens.segmentation import (
    MemoryStore, SegmentationParams, Segmenter, geojson_method_member, haversine_m as _haversine_m,
)

BBOX_HOUSTON = (-95.70, 29.10, -94.20, 30.10)  # west, south, east, north
ALIASES = {
    "mmsi": ("MMSI","mmsi"),
    "timestamp": ("BaseDateTime","BASE_DATE_TIME","time"),
    "lat": ("LAT","Lat","latitude"),
    "lon": ("LON","Lon","longitude"),
    "sog": ("SOG","sog"),
    "vessel_type": ("VesselType","vessel_type"),
    "nav_status": ("Status","nav_status","NavigationStatus"),
    "cog": ("COG","cog"),
    "heading": ("Heading","heading"),
    "length": ("Length","length"),
    "width": ("Width","width"),
    "draft": ("Draft","draft"),
    "transceiver": ("TransceiverClass","transceiver_class","transceiver"),
}
OPTIONAL_COLUMNS = ("vessel_type","nav_status","cog","heading","length","width","draft","transceiver")
# Required AIS columns, in the order a missing-column error names the first gap.
REQUIRED_COLUMNS = tuple(name for name in ALIASES if name not in OPTIONAL_COLUMNS)
# New columns are appended so positional consumers of earlier files keep working (#39).
CLEAN_FIELDS = ["mmsi","timestamp_utc","lat","lon","sog_knots","vessel_type","nav_status",
                "cog_deg","heading_deg","length_m","width_m","draft_m","transceiver_class","mmsi_category"]
# Free text copied from the AIS row. Neutralized on write and recovered on read.
# Numeric columns and mmsi are not in this set, so -95.1 is never prefixed.
CLEANED_FREE_TEXT = ("vessel_type", "nav_status")
EVENT_FIELDS = ["event_id","mmsi","start_utc","end_utc","duration_min","point_count",
                "centroid_lon","centroid_lat","maximum_distance_m","type","method_version","parameter_set",
                "confidence_label","left_censoring","right_censoring",
                "vessel_type","transceiver_class","length_m","draft_m","mmsi_category"]

# How many header names a missing-column error shows, and how long each shown name is.
_FOUND_NAME_LIMIT = 10
_FOUND_NAME_CHARS = 40

def _escape_shown_text(value):
    """One header name, escaped, then capped for the error line."""
    rendered=escape_error_text(value)
    if len(rendered) > _FOUND_NAME_CHARS:
        return rendered[:_FOUND_NAME_CHARS] + "..."
    return rendered

def _format_found_columns(header):
    """First names of a header, escaped and capped, for an error line."""
    names=list(header)
    shown=[_escape_shown_text(column) for column in names[:_FOUND_NAME_LIMIT]]
    text=", ".join(shown)
    extra=len(names) - len(shown)
    if extra:
        suffix=f"... (+{extra} more)"
        text=f"{text}, {suffix}" if text else suffix
    return text

def header_alias(header, name, required=True, source=None):
    indexed={x.lower().strip():x for x in header}
    for candidate in ALIASES[name]:
        if candidate.lower() in indexed:
            return indexed[candidate.lower()]
    if required:
        found=_format_found_columns(header)
        where=f"input file '{source}'" if source is not None else "input file"
        expected=", ".join(REQUIRED_COLUMNS)
        raise AISInputError(
            f"{where} is missing required column '{name}' (found: {found}). "
            f"Expected required AIS columns: {expected} (aliases are listed in the data dictionary)."
        )
    return None

def _cannot_write_directory(directory, exc):
    detail=exc.strerror if exc.strerror else type(exc).__name__
    return AISInputError(f"cannot write output directory '{directory}' ({detail}).")

def _absolute_lexical(path):
    """Absolute path with ``.`` and ``..`` collapsed. Symlinks are not resolved."""
    return Path(os.path.abspath(path))

def _lstat_or_none(path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None

def _followed_directory(path, requested):
    """True when ``path`` is a directory, following one pre-existing symlink.

    A dangling symlink and a symlink to a non-directory are refused. A real
    directory is accepted. The symlink itself is not recorded as created.
    """
    info=_lstat_or_none(path)
    if info is None:
        raise AISInputError(f"cannot write output directory '{requested}' (missing).")
    if stat.S_ISLNK(info.st_mode):
        try:
            followed=os.stat(path)
        except OSError as exc:
            raise AISInputError(
                f"cannot write output directory '{requested}' (symlink)."
            ) from exc
        if not stat.S_ISDIR(followed.st_mode):
            raise AISInputError(
                f"cannot write output directory '{requested}' (not a directory)."
            )
        return True
    if not stat.S_ISDIR(info.st_mode):
        raise AISInputError(
            f"cannot write output directory '{requested}' (not a directory)."
        )
    return False

def _open_directory(path, requested):
    """Open ``path`` for ``mkdir``. Follow a pre-existing symlink to a directory.

    A real directory is opened with ``O_NOFOLLOW``. A symlink to a directory
    is opened without that flag so the next component is created in the
    target, which is what ``/tmp`` does on macOS.
    """
    follow=_followed_directory(path, requested)
    flags=os.O_RDONLY|os.O_DIRECTORY
    if not follow:
        flags|=os.O_NOFOLLOW
    try:
        return os.open(path, flags)
    except OSError as exc:
        raise _cannot_write_directory(requested, exc) from exc

def _same_directory(path, dev, ino):
    """True when ``path`` is still the real directory recorded at ``mkdir``."""
    info=_lstat_or_none(path)
    if info is None or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return False
    return info.st_dev==dev and info.st_ino==ino

class _OwnedFile:
    """One regular file this run created, identified after its final write.

    ``st_dev`` and ``st_ino`` alone are not enough: an unlink can free the
    inode, and the next create can reuse the number. Cleanup also compares
    ``st_size``, ``st_mtime_ns``, and ``st_ctime_ns`` from the snapshot taken
    after the last byte. A mismatch leaves the path in place. ``os.lstat``
    does not follow the final component, so a symlink is left in place.
    """

    def __init__(self, path, info):
        self.path=Path(path)
        self.dev=info.st_dev
        self.ino=info.st_ino
        self.size=info.st_size
        self.mtime_ns=info.st_mtime_ns
        self.ctime_ns=info.st_ctime_ns

    def adopt(self, info):
        """Replace the snapshot with ``info`` from a later fstat or lstat."""
        self.dev=info.st_dev
        self.ino=info.st_ino
        self.size=info.st_size
        self.mtime_ns=info.st_mtime_ns
        self.ctime_ns=info.st_ctime_ns

    def matches(self, info):
        return (stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
                and info.st_dev==self.dev and info.st_ino==self.ino
                and info.st_size==self.size and info.st_mtime_ns==self.mtime_ns
                and info.st_ctime_ns==self.ctime_ns)

def _unlink_owned(owned):
    """Unlink ``owned`` only when the path still has its recorded identity."""
    info=_lstat_or_none(owned.path)
    if info is None or not owned.matches(info):
        return
    try:
        os.unlink(owned.path)
    except OSError:
        return

class _ExclusiveText:
    """Text writer for an fd this run created. The snapshot is taken on close.

    ``os.fdopen`` owns the fd. ``__exit__`` flushes, then ``fstat``s, then
    closes, so the recorded size and timestamps include the bytes just written.
    """

    def __init__(self, owned, fd, newline):
        self.owned=owned
        self.handle=os.fdopen(fd, "w", encoding="utf-8", newline=newline)

    def __enter__(self):
        return self.handle

    def __exit__(self, exc_type, exc, tb):
        fd=self.handle.fileno()
        try:
            self.handle.flush()
        except Exception:
            pass
        try:
            self.owned.adopt(os.fstat(fd))
        except OSError:
            pass
        self.handle.close()
        return False

def _rmdir_same_directory(path, dev, ino):
    """Remove one empty directory this run created. False if it stays.

    A symlink, or a directory whose identity changed, is not removed.
    ``os.lstat`` does not follow the final component. A non-empty directory
    stops the caller.
    """
    if not _same_directory(path, dev, ino):
        return True
    try:
        with os.scandir(path) as found:
            if any(True for _ in found):
                return False
        os.rmdir(path)
    except OSError:
        return False
    return True

class OutputScope:
    """Directories this call created, and files this call created.

    The path is lexical (``os.path.abspath``), not ``Path.resolve()``, so
    ``nope/../results`` is the existing ``results`` and not a new ``nope``.
    Each new component is created with ``os.mkdir``. A pre-existing symlink
    to a directory is followed, so a symlinked parent such as macOS ``/tmp``
    still receives the new directory. A dangling symlink and a symlink to a
    non-directory are refused. ``FileExistsError`` means the component is
    not ours and is not recorded. Cleanup unlinks a recorded file only when
    its device, inode, size, and timestamps still match, and does not unlink
    a symlink. It then ``rmdir``s recorded directories
    that are still empty, deepest first, and does not remove the pre-existing
    symlink.
    """

    def __init__(self, directory):
        self.directory=_absolute_lexical(directory)
        self.created_dirs=[]
        self.owned_files=[]

    def ensure(self):
        directory=self.directory
        anchor=Path(directory.anchor)
        relative=directory.relative_to(anchor)
        created=[]
        current=anchor
        try:
            if str(relative)!=".":
                for part in relative.parts:
                    nxt=current/part
                    parent_fd=_open_directory(current, directory)
                    try:
                        try:
                            os.mkdir(part, dir_fd=parent_fd)
                        except FileExistsError:
                            _followed_directory(nxt, directory)
                        except OSError as exc:
                            raise _cannot_write_directory(directory, exc) from exc
                        else:
                            info=os.stat(part, dir_fd=parent_fd, follow_symlinks=False)
                            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                                raise AISInputError(
                                    f"cannot write output directory '{directory}' (symlink)."
                                )
                            created.append((nxt, info.st_dev, info.st_ino))
                    finally:
                        os.close(parent_fd)
                    current=nxt
        except BaseException:
            _rollback_created(created)
            raise
        self.created_dirs=created
        return self.directory

    def verify_created(self):
        """Refuse when a directory this run created was replaced by a symlink."""
        for path, dev, ino in self.created_dirs:
            if not _same_directory(path, dev, ino):
                raise AISInputError(
                    f"cannot write output directory '{self.directory}' (symlink)."
                )

    def artifact_is_new(self, path):
        """Refuse a symlink final component. True when the path is absent."""
        self.refuse_artifact_symlink(path)
        return _lstat_or_none(path) is None

    def refuse_artifact_symlink(self, path):
        """Refuse to write or delete through a symlink at the final component."""
        info=_lstat_or_none(path)
        if info is not None and stat.S_ISLNK(info.st_mode):
            raise AISInputError(f"cannot write output file '{path}' (symlink).")

    def claim_file(self, path):
        """Record identity after this run's final write of an existing path.

        The snapshot includes size and timestamps, not only the inode number.
        """
        path=Path(path)
        info=os.lstat(path)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AISInputError(f"cannot write output file '{path}' (symlink).")
        self.owned_files.append(_OwnedFile(path, info))

    def open_exclusive(self, path, newline=""):
        """Create ``path`` with ``O_CREAT|O_EXCL`` and record it before any write.

        The returned context manager seals size and timestamps when it closes,
        including when the write raises. A symlink at ``path`` is not followed.
        ``FileExistsError`` propagates so the caller can keep its own message.
        """
        path=Path(path)
        flags=os.O_CREAT|os.O_EXCL|os.O_WRONLY
        if hasattr(os, "O_CLOEXEC"):
            flags|=os.O_CLOEXEC
        if hasattr(os, "O_NOFOLLOW"):
            flags|=os.O_NOFOLLOW
        try:
            fd=os.open(os.fspath(path), flags, 0o644)
        except FileExistsError:
            raise
        except OSError as exc:
            if exc.errno==errno.ELOOP:
                raise AISInputError(f"cannot write output file '{path}' (symlink).") from exc
            detail=exc.strerror if exc.strerror else type(exc).__name__
            raise AISInputError(
                f"cannot write output directory '{self.directory}' ({detail})."
            ) from exc
        try:
            info=os.fstat(fd)
        except OSError:
            os.close(fd)
            raise
        owned=_OwnedFile(path, info)
        self.owned_files.append(owned)
        return _ExclusiveText(owned, fd, newline)

    def cleanup(self):
        for owned in self.owned_files:
            _unlink_owned(owned)
        _rollback_created(self.created_dirs)

def _rollback_created(created):
    for path, dev, ino in reversed(created):
        if not _rmdir_same_directory(path, dev, ino):
            return

def _publish(path, write, scope=None):
    """Write ``path`` via a private temp file and ``os.replace`` this one file.

    The temp name is random (``tempfile.mkstemp``), so a pre-planted symlink
    at ``<name>.partial`` is not opened. The file mode is ``0o644`` before
    the replace. A failure deletes the temp file only when its ``st_dev``,
    ``st_ino``, ``st_size``, ``st_mtime_ns``, and ``st_ctime_ns`` still match
    the snapshot taken after the last byte, and leaves ``path`` in place.
    This replaces one file, not the whole output set. ``os.replace`` replaces
    a symlink at ``path`` and does not write the link target; that is the
    case main already accepts. A file that did not exist before the replace
    is recorded with that same snapshot after ``os.replace``. ``OSError``,
    including ``FileNotFoundError`` and ``NotADirectoryError``, becomes one
    domain-error line.
    """
    path=Path(path)
    if scope is not None:
        scope.verify_created()
    # ``os.replace`` replaces a symlink node and does not follow it. A
    # pre-existing symlink at this name is the case main already accepts.
    existed=_lstat_or_none(path) is not None
    fd=None
    partial=None
    published=False
    owned=None
    try:
        try:
            fd, raw=tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".partial")
            partial=Path(raw)
            owned=_OwnedFile(partial, os.fstat(fd))
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
                fd=None
                try:
                    write(handle)
                finally:
                    try:
                        handle.flush()
                    except Exception:
                        pass
                    try:
                        owned.adopt(os.fstat(handle.fileno()))
                    except OSError:
                        pass
            info=_lstat_or_none(partial)
            if info is None or not owned.matches(info):
                raise AISInputError(
                    f"cannot write output directory '{path.parent}' (temp file was replaced)."
                )
            os.chmod(partial, 0o644)
            owned.adopt(os.lstat(partial))
            os.replace(partial, path)
            published=True
            if scope is not None and not existed:
                scope.claim_file(path)
        except AISInputError:
            raise
        except OSError as exc:
            raise _cannot_write_directory(path.parent, exc) from exc
    finally:
        if fd is not None:
            os.close(fd)
        if owned is not None and not published:
            _unlink_owned(owned)

def _resolve_columns(header, source):
    """Map logical columns. The first missing required name follows REQUIRED_COLUMNS."""
    cols={}
    for name in REQUIRED_COLUMNS:
        cols[name]=header_alias(header, name, True, source)
    for name in OPTIONAL_COLUMNS:
        cols[name]=header_alias(header, name, False, source)
    return cols

def sha256(path):
    h=hashlib.sha256()
    try:
        with path.open("rb") as source:
            for block in iter(lambda:source.read(8*1024*1024),b""):
                h.update(block)
    except OSError as exc:
        raise AISInputError("Input file cannot be accessed") from exc
    return h.hexdigest()

def parse_time(value):
    """Parse a NOAA-style AIS timestamp as aware UTC.

    Naive ``YYYY-MM-DDTHH:MM:SS`` and the same form with one space instead
    of ``T`` are UTC. ``Z``, ``+00:00``, and other ``±HH:MM`` offsets are
    accepted; a non-UTC offset is converted to UTC. The fraction is absent
    or 1 to 6 digits. See ``harborlens.timeparse.parse_observation_time``.
    A bad value is a per-row ``ValueError`` so ingestion can count it as
    invalid. It is not an ``AISInputError``.
    """
    return parse_observation_time(value)

def ingest(source, output, bbox=BBOX_HOUSTON, max_rows=None, *, before_publish=None, scope=None):
    if max_rows is not None and max_rows < 0:
        raise AISInputError("max_rows must not be negative")
    if len(bbox) != 4 or not all(math.isfinite(float(x)) for x in bbox):
        raise AISInputError("Bounding box must have four finite numbers")
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise AISInputError("Bounding box must be ordered west,south,east,north")
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise AISInputError("Input and output paths must be different")
    # Read the header before creating an output file so a missing file, an
    # empty file, or a missing required column leaves no partial CSV.
    row_iter=iter(stream_rows(source))
    try:
        try:
            peeked=next(row_iter)
        except StopIteration:
            peeked=None
        cols=_resolve_columns(list(peeked), source) if peeked is not None else None
        try:
            output.parent.mkdir(parents=True,exist_ok=True)
        except OSError as exc:
            raise _cannot_write_directory(output.parent, exc) from exc
        # One file is replaced only after it is fully written. A failure here
        # leaves an existing cleaned CSV in place. Later files are separate.
        counts=dict(total=0,in_bbox=0,missing_value=0,invalid=0,outside_bbox=0,duplicate=0,written=0)
        seen=set()
        first=last=None
        truncated=False
        categories={}
        holder={}
        def write_cleaned(handle):
            nonlocal first, last, truncated
            writer=CsvDictWriter(handle,CLEAN_FIELDS)
            rows=() if peeked is None else itertools.chain((peeked,), row_iter)
            for row in rows:
                    if max_rows is not None and counts["total"]>=max_rows:
                        truncated=True
                        break
                    counts["total"]+=1
                    if any(not str(row.get(cols[k]) or "").strip() for k in ("mmsi","timestamp","lat","lon","sog")):
                        # Empty required field: "not available" (2025+ archives write nulls), not corrupt data.
                        counts["missing_value"]+=1
                        continue
                    try:
                        mmsi=str(row[cols["mmsi"]]).strip()
                        t=parse_time(row[cols["timestamp"]])
                        lat=float(row[cols["lat"]])
                        lon=float(row[cols["lon"]])
                        sog=float(row[cols["sog"]])
                        if not (mmsi.isascii() and mmsi.isdigit()) or len(mmsi) not in (8,9):
                            raise ValueError("invalid MMSI")
                        if not (math.isfinite(lat) and math.isfinite(lon) and math.isfinite(sog)) or not (-90<=lat<=90 and -180<=lon<=180 and 0<=sog<=100):
                            raise ValueError("coordinate or speed out of range")
                    except (ValueError,TypeError,KeyError,OverflowError):
                        counts["invalid"]+=1
                        continue
                    if not (bbox[0]<=lon<=bbox[2] and bbox[1]<=lat<=bbox[3]):
                        counts["outside_bbox"]+=1
                        continue
                    counts["in_bbox"]+=1
                    key=(mmsi,t.isoformat(),round(lat,6),round(lon,6))
                    if key in seen:
                        counts["duplicate"]+=1
                        continue
                    seen.add(key)
                    get=lambda name:row.get(cols[name],"") if cols[name] else ""  # noqa: E731
                    attributes=normalize_attributes(get("cog"),get("heading"),get("length"),get("width"),
                                                    get("draft"),get("transceiver"))
                    category=mmsi_category(mmsi)
                    categories[category]=categories.get(category,0)+1
                    writer.writerow({
                        "mmsi":mmsi,"timestamp_utc":t.isoformat().replace("+00:00","Z"),
                        "lat":lat,"lon":lon,"sog_knots":sog,
                        "vessel_type":neutralize_text_cell(get("vessel_type")),
                        "nav_status":neutralize_text_cell(get("nav_status")),
                        **{k:csv_value(v) for k,v in attributes.items()},"mmsi_category":category,
                    })
                    counts["written"]+=1
                    first=t if first is None or t<first else first
                    last=t if last is None or t>last else last
            holder["result"]={"input_file":str(source),"input_sha256":sha256(source),"output":str(output),
                    "bbox_lon_lat":list(bbox),"counts":counts,"note":"QA counts, not port-call statistics",
                    "input_truncated":truncated,"limits":{"max_rows":max_rows},
                    "mmsi_categories":dict(sorted(categories.items())),
                    "observed_time_range":observed_range(first,last)}
            # A refusal here runs before ``os.replace``, so an existing cleaned
            # CSV is left byte-for-byte. The temp file is deleted by ``_publish``.
            if before_publish is not None:
                before_publish(holder["result"])
        _publish(output, write_cleaned, scope)
        return holder["result"]
    finally:
        row_iter.close()

# Kept for callers that import it from this module; the engine owns the implementation.
haversine_m = _haversine_m

# In-memory consumers hold ~470 bytes per cleaned row (measured on 3.9 million rows:
# ~1.8 GiB RSS). The cap bounds memory at roughly 2.8 GiB and fails before loading more.
MAX_IN_MEMORY_ROWS = 6_000_000

def interpret_cleaned_row(row):
    """Logical cells of one ``houston_clean.csv`` row.

    ``vessel_type`` and ``nav_status`` are recovered with the shared reader.
    ``mmsi``, timestamps, and numeric columns stay the raw cell text. A
    leading apostrophe on those columns is not removed. The release recount
    uses this function and still counts raw MMSI strings.
    """
    interpreted=dict(row)
    for field in CLEANED_FREE_TEXT:
        if field in interpreted:
            interpreted[field]=recover_text_cell(interpreted.get(field) or "")
    return interpreted

def load_cleaned(cleaned,max_rows=MAX_IN_MEMORY_ROWS):
    """Read canonical cleaned AIS and return rows sorted by (mmsi, time, file order).

    Rows that cannot be parsed are counted, not silently dropped. More than
    ``max_rows`` rows fails closed while reading, before memory grows further.
    """
    rows=[]
    unparsable=0
    with Path(cleaned).open("r",newline="",encoding="utf-8") as stream:
        for index,row in enumerate(csv.DictReader(stream)):
            if index>=max_rows:
                raise AISInputError("Cleaned AIS exceeds the in-memory row cap; refusing a partial result")
            try:
                interpreted=interpret_cleaned_row(row)
                rows.append((str(interpreted["mmsi"]),parse_time(interpreted["timestamp_utc"]),float(interpreted["lat"]),
                             float(interpreted["lon"]),float(interpreted["sog_knots"]),
                             str(interpreted.get("vessel_type") or ""),index,
                             parse_csv_attributes(interpreted)))
            except (ValueError,TypeError,KeyError):
                unparsable+=1
    rows.sort(key=lambda r:(r[0],r[1],r[6]))
    return rows,unparsable

def segment_rows(rows,params,censoring=None,unparsable=0):
    """Run the shared engine over pre-sorted rows from ``load_cleaned``."""
    if censoring is None:
        censoring=WindowCensoring(None,params.max_gap_minutes)
    events=[]
    engine=Segmenter(params,MemoryStore(),lambda record,group:events.append(record),censoring)
    for mmsi,when,lat,lon,sog,vessel_type,index,attributes in rows:
        engine.feed(mmsi,when,lat,lon,sog,vessel_type,index,attributes)
    stats=engine.close()
    stats["unparsable_rows"]=unparsable
    stats["censoring"]=censoring.event_summary()
    stats["warning"]="Stationary candidates are unvalidated, NOT verified berth, anchorage, waiting, or port calls."
    return events,stats

def infer_candidates(cleaned, max_sog=0.5, min_duration_minutes=30,
                     max_gap_minutes=15, max_radius_m=1000, min_points=8, censoring=None,
                     max_jump_knots=65, params=None):
    """Return unvalidated stationary candidates and run statistics (shared engine, #37).

    ``params`` (SegmentationParams) overrides the individual threshold keywords.
    ``censoring`` is an optional WindowCensoring; without it every candidate's
    left/right censoring is reported as ``unknown`` (BR-019).
    """
    if params is None:
        params=SegmentationParams(max_sog,min_duration_minutes,max_gap_minutes,
                                  max_radius_m,min_points,max_jump_knots)
    rows,unparsable=load_cleaned(cleaned)
    return segment_rows(rows,params,censoring,unparsable)

# Typed columns of stationary_candidates.csv (schemas/v1/stationary-candidate.schema.json);
# all other columns are strings.
CANDIDATE_CSV_TYPES={"duration_min":float,"point_count":int,"centroid_lon":float,
                     "centroid_lat":float,"maximum_distance_m":float}
# Optional columns: an empty cell means "not available" and reads back as None.
CANDIDATE_CSV_OPTIONAL={"length_m":float,"draft_m":float,"transceiver_class":str}

def read_candidates_csv(path):
    """Read stationary_candidates.csv back into typed records matching the candidate schema."""
    with Path(path).open(newline="",encoding="utf-8") as stream:
        def convert(k,v):
            if k == "vessel_type":
                v=recover_text_cell(v)
            if k in CANDIDATE_CSV_OPTIONAL:
                return CANDIDATE_CSV_OPTIONAL[k](v) if v!="" else None
            return CANDIDATE_CSV_TYPES[k](v) if k in CANDIDATE_CSV_TYPES else v
        return [{k:convert(k,v) for k,v in row.items() if k in EVENT_FIELDS}
                for row in csv.DictReader(stream)]

def write_events(events,out,params=None,scope=None):
    params=params or SegmentationParams()
    out.mkdir(parents=True,exist_ok=True)

    def write_csv(handle):
        writer=CsvDictWriter(handle,EVENT_FIELDS)
        for event in events:
            # Copy so GeoJSON keeps the logical vessel_type. JSON strings are not formulas.
            row={field:event[field] for field in EVENT_FIELDS}
            row["vessel_type"]=neutralize_text_cell(row["vessel_type"])
            writer.writerow(row)

    def write_geojson(handle):
        features=[{"type":"Feature","geometry":{"type":"Point","coordinates":[e["centroid_lon"],e["centroid_lat"]]},
                   "properties":{k:v for k,v in e.items() if k not in ("centroid_lon","centroid_lat")}} for e in events]
        collection={"type":"FeatureCollection","harborlens_method":geojson_method_member(params),"features":features}
        handle.write(json.dumps(collection,indent=2))

    _publish(out/"stationary_candidates.csv", write_csv, scope)
    _publish(out/"stationary_candidates.geojson", write_geojson, scope)

def run(src,out,bbox=BBOX_HOUSTON,max_rows=None,source_url=None,window_start=None,window_end=None,
        params=None):
    """Ingest one AIS file, infer candidates and write a provenance manifest.

    The analysis window comes from ``window_start``/``window_end`` or from a
    verified acquisition sidecar next to ``src``. A run truncated by
    ``max_rows`` reports censoring as unknown, because its effective end is unknown.
    ``params`` (SegmentationParams) defaults to the documented BR-003 thresholds.
    An invalid ``source_url`` is refused before any output file is written.
    A requested ``--window-start``/``--window-end`` is checked, with
    ``declared_window``, before any directory is created and before ingest.
    On failure, only files this call created are removed, then only
    directories this call created that are still empty. A pre-existing
    file, including one inside a directory this call created, is not deleted.
    The original error is re-raised.
    """
    params=params or SegmentationParams()
    require_declared_source_url(source_url)
    # No ingest, download, or write until the requested window is acceptable.
    declared_window(window_start, window_end)
    src=Path(src)
    scope=OutputScope(out)
    failed=True
    try:
        scope.ensure()
        out=scope.directory
        cleaned=out/"houston_clean.csv"

        def before_publish(partial):
            pending=resolve_input_window(src,partial["input_sha256"],window_start,window_end)
            if pending is not None and partial["input_truncated"]:
                return
            observed=partial["observed_time_range"]
            if pending is not None and observed["start_utc"]:
                WindowCensoring([pending],params.max_gap_minutes).check_observed(
                    parse_utc(observed["start_utc"]),parse_utc(observed["end_utc"]))

        manifest=ingest(src,cleaned,bbox,max_rows,before_publish=before_publish, scope=scope)
        window=resolve_input_window(src,manifest["input_sha256"],window_start,window_end)
        declaration=declaration_record(src.name,window)
        if window is not None and manifest["input_truncated"]:
            declaration["ignored_reason"]="input_truncated_by_max_rows"
            window=None
        censoring=WindowCensoring([window] if window else None,params.max_gap_minutes,[declaration])
        observed=manifest.pop("observed_time_range")
        if observed["start_utc"]:
            censoring.check_observed(parse_utc(observed["start_utc"]),parse_utc(observed["end_utc"]))
        events,stats=infer_candidates(cleaned,censoring=censoring,params=params)
        write_events(events,out,params,scope)
        manifest["events"]=stats
        manifest["method_parameters"]=params.manifest()
        manifest["analysis_window"]=censoring.summary(observed)
        manifest = add_provenance(out, manifest, source_url=source_url)
        body=json.dumps(manifest,indent=2)
        _publish(out/"manifest.json", lambda handle: handle.write(body), scope)
        failed=False
        return manifest
    finally:
        if failed:
            scope.cleanup()
