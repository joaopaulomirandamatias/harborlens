"""Bounded-memory multi-file AIS stationary-candidate reconstruction (SPEC-002).

Use a temporary SQLite database to sort observations across multiple local
historical AIS subsets. No network activity, live tracking, navigation guidance,
validated port-call labels, or real-world accuracy claims are provided.

Data remain in a private temporary directory and are deleted on exit.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harborlens.ais import (
    BBOX_HOUSTON, CLEAN_FIELDS, EVENT_FIELDS, header_alias, parse_time, sha256,
)
from harborlens.segmentation import (
    METHOD_VERSION, SegmentationParams, Segmenter, add_threshold_arguments,
    geojson_method_member, params_from_args,
)
from harborlens.io_safe import AISInputError, stream_rows
from harborlens.provenance import checksum, FILES
from harborlens.censoring import (
    AnalysisWindowError, WindowCensoring, declaration_record, declared_window,
    observed_range, sidecar_window,
)

METHOD = METHOD_VERSION
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
ONE_MICROSECOND = timedelta(microseconds=1)
MULTIDAY_FIELDS = EVENT_FIELDS + ["source_files_json", "source_count", "crosses_utc_date"]
MAX_FILES = 7
# Ceilings sized from a synthetic benchmark (~161 bytes of SQLite scratch per row,
# ~47 MiB RSS independent of size, ~20 s per million rows) for seven full Houston
# days (~3.9 million rows) with headroom. Limits still fail closed.
MAX_POINTS = 6_000_000
MAX_SCRATCH_MIB = 2048
MAX_EXPORT_MIB = 2048
DEFAULT_EXPORT_MIB = 1024


def _csv_bytes(fields):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerow(fields)
    return stream.getvalue().encode("utf-8")


class ScratchMeter:
    """Checks the SQLite scratch size against its cap and remembers the peak seen."""

    def __init__(self, db_path, cap_bytes):
        self.db_path = Path(db_path)
        self.cap_bytes = cap_bytes
        self.peak_bytes = 0

    def check(self):
        # The scratch database is deleted even on failure. Include journal bytes.
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        journal = self.db_path.with_name(self.db_path.name + "-journal")
        if journal.exists():
            size += journal.stat().st_size
        self.peak_bytes = max(self.peak_bytes, size)
        if size > self.cap_bytes:
            raise AISInputError("Multi-day SQLite scratch store exceeded configured disk cap")
        return size


def _make_db(path, max_scratch_mib):
    db = sqlite3.connect(str(path))
    db.execute("PRAGMA synchronous=OFF")
    db.execute("PRAGMA journal_mode=DELETE")
    db.execute("PRAGMA temp_store=FILE")
    db.execute("PRAGMA cache_size=-8192")
    db.execute("PRAGMA page_size=4096")
    db.execute(f"PRAGMA max_page_count={max_scratch_mib * 1024 * 1024 // 4096}")
    db.executescript(
        """
        CREATE TABLE observations (
          id INTEGER PRIMARY KEY,
          mmsi TEXT NOT NULL,
          ts TEXT NOT NULL,
          epoch_us INTEGER NOT NULL,
          lat REAL NOT NULL,
          lon REAL NOT NULL,
          sog REAL NOT NULL,
          vessel_type TEXT NOT NULL,
          nav_status TEXT NOT NULL,
          lat_micro INTEGER NOT NULL,
          lon_micro INTEGER NOT NULL
        );
        CREATE UNIQUE INDEX unique_observation
          ON observations(mmsi, ts, lat_micro, lon_micro);
        CREATE TABLE observation_sources (
          observation_id INTEGER NOT NULL,
          source_id INTEGER NOT NULL,
          PRIMARY KEY(observation_id, source_id)
        ) WITHOUT ROWID;
        CREATE TABLE group_observations (
          group_id INTEGER NOT NULL,
          observation_id INTEGER NOT NULL
        );
        CREATE INDEX group_observations_by_group
          ON group_observations(group_id);
        """
    )
    return db


def _load_files(db, inputs, bbox, max_points, meter):
    counts = {
        "total": 0, "invalid": 0, "outside_bbox": 0, "duplicate": 0,
        "duplicate_across_files": 0, "written": 0,
    }
    source_items = []
    first = last = None
    w, s, e, n = bbox
    row_inserts = db.cursor()
    for source_id, path in enumerate(inputs):
        path = Path(path)
        item = {
            "source_id": source_id,
            "filename": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
            "rights_status": "review_required",
        }
        item["source_ref"] = f"{path.name}@{item['sha256'][:12]}"
        source_items.append(item)
        columns = None
        file_rows = 0
        for row in stream_rows(path):
            if columns is None:
                columns = {
                    key: header_alias(list(row), key, required=key not in ("vessel_type", "nav_status"))
                    for key in ("mmsi", "timestamp", "lat", "lon", "sog", "vessel_type", "nav_status")
                }
            file_rows += 1
            counts["total"] += 1
            if counts["total"] > max_points:
                raise AISInputError("Input records exceed cap; refusing truncated multi-day result")
            try:
                mmsi = str(row[columns["mmsi"]]).strip()
                moment = parse_time(row[columns["timestamp"]])
                timestamp = moment.isoformat().replace("+00:00", "Z")
                lat = float(row[columns["lat"]])
                lon = float(row[columns["lon"]])
                sog = float(row[columns["sog"]])
                if not mmsi.isdigit() or len(mmsi) not in (8, 9):
                    raise ValueError("invalid MMSI")
                if not (
                    math.isfinite(lat) and math.isfinite(lon) and math.isfinite(sog)
                    and -90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= sog <= 100
                ):
                    raise ValueError("invalid coordinate or speed")
            except (KeyError, TypeError, ValueError, OverflowError):
                counts["invalid"] += 1
                continue
            if not (w <= lon <= e and s <= lat <= n):
                counts["outside_bbox"] += 1
                continue
            vessel_type = str(row.get(columns["vessel_type"], "") or "") if columns["vessel_type"] else ""
            nav_status = str(row.get(columns["nav_status"], "") or "") if columns["nav_status"] else ""
            key = (mmsi, timestamp, round(lat * 1_000_000), round(lon * 1_000_000))
            row_inserts.execute(
                """INSERT OR IGNORE INTO observations
                   (mmsi,ts,epoch_us,lat,lon,sog,vessel_type,nav_status,lat_micro,lon_micro)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (mmsi, timestamp, (moment - EPOCH) // ONE_MICROSECOND,
                 lat, lon, sog, vessel_type, nav_status, key[2], key[3]),
            )
            first = moment if first is None or moment < first else first
            last = moment if last is None or moment > last else last
            if row_inserts.rowcount:
                obs_id = row_inserts.lastrowid
                counts["written"] += 1
            else:
                counts["duplicate"] += 1
                obs_id = db.execute(
                    """SELECT id FROM observations
                       WHERE mmsi=? AND ts=? AND lat_micro=? AND lon_micro=?""", key
                ).fetchone()[0]
                existing = db.execute(
                    "SELECT 1 FROM observation_sources WHERE observation_id=? AND source_id<>? LIMIT 1",
                    (obs_id, source_id),
                ).fetchone()
                if existing:
                    counts["duplicate_across_files"] += 1
            db.execute(
                "INSERT OR IGNORE INTO observation_sources(observation_id,source_id) VALUES (?,?)",
                (obs_id, source_id),
            )
            if counts["total"] % 5000 == 0:
                db.commit()
                meter.check()
        if file_rows == 0:
            raise AISInputError(f"Source has no AIS observations: {path.name}")
        item["rows_scanned"] = file_rows
        db.commit()
        meter.check()
    return counts, source_items, (first, last)


def _resolve_windows(paths, source_items, window_start, window_end, tolerance_minutes):
    """Build censoring blocks from verified per-input sidecars or one explicit window.

    All inputs must carry a verified sidecar for the sidecar windows to be used;
    a partial set yields ``unknown`` censoring rather than a misleading union.
    """
    sides = [sidecar_window(path, item["sha256"]) for path, item in zip(paths, source_items)]
    explicit = declared_window(window_start, window_end)
    if any(sides):
        if explicit:
            raise AnalysisWindowError(
                "Inputs carry verified acquisition windows; do not also pass --window-start/--window-end"
            )
        declarations = [declaration_record(item["filename"], side)
                        for item, side in zip(source_items, sides)]
        windows = sides if all(sides) else None
    elif explicit:
        declarations = [declaration_record("all_inputs", explicit)]
        windows = [explicit]
    else:
        declarations = [declaration_record(item["filename"], None) for item in source_items]
        windows = None
    return WindowCensoring(windows, tolerance_minutes, declarations)


def _output_files(out):
    return {name: out / name for name in (*FILES, "manifest.json")}


def run_multiday(
    inputs,
    out,
    bbox=BBOX_HOUSTON,
    max_points=MAX_POINTS,
    max_scratch_mib=MAX_SCRATCH_MIB,
    max_export_mib=DEFAULT_EXPORT_MIB,
    max_sog=0.5,
    min_duration_minutes=30,
    max_gap_minutes=15,
    max_radius_m=1000,
    min_points=8,
    max_jump_knots=65,
    window_start=None,
    window_end=None,
    params=None,
):
    """Reconstruct provisional stationary candidates across 2–7 local AIS files.

    Only bounded counters and a current candidate are held in Python memory;
    full sorted points and group membership live in temporary SQLite on disk.
    """
    paths = tuple(sorted((Path(p).resolve() for p in inputs), key=str))
    if not 2 <= len(paths) <= MAX_FILES or len(set(paths)) != len(paths):
        raise AISInputError("Provide 2–7 distinct AIS files")
    if not all(path.is_file() for path in paths):
        raise AISInputError("All source files must exist")
    if not (1 <= max_points <= MAX_POINTS and 16 <= max_scratch_mib <= MAX_SCRATCH_MIB
            and 1 <= max_export_mib <= MAX_EXPORT_MIB):
        raise AISInputError("Input, scratch or export caps outside permitted limits")
    if (len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox)
            or not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90)):
        raise AISInputError("Invalid west/south/east/north research bounding box")
    if params is None:
        params = SegmentationParams(max_sog, min_duration_minutes, max_gap_minutes,
                                    max_radius_m, min_points, max_jump_knots)
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = _output_files(out)
    if any(path in paths or path.exists() for path in files.values()):
        raise FileExistsError("Output files already exist or would overwrite a source")

    # Use a private ephemeral scratch directory; never commit or upload AIS.
    with tempfile.TemporaryDirectory(prefix="harborlens-scratch-") as folder:
        db_path = Path(folder) / "ais.sqlite3"
        db = _make_db(db_path, max_scratch_mib)
        meter = ScratchMeter(db_path, max_scratch_mib * 1048576)
        try:
            counts, source_items, (first, last) = _load_files(
                db, paths, tuple(bbox), max_points, meter
            )
            db.commit()
            censoring = _resolve_windows(paths, source_items, window_start, window_end,
                                         params.max_gap_minutes)
            censoring.check_observed(first, last)
            diagnostics = _write_outputs(db, files, source_items, params, max_export_mib, censoring, meter)
            db.commit()
            meter.check()
            diagnostics["censoring"] = censoring.event_summary()
            diagnostics["warning"] = ("Only unvalidated stationary candidates, "
                                      "not confirmed berths or waiting vessels.")
            identity = {"source_hashes": sorted(x["sha256"] for x in source_items),
                        "bbox": list(bbox), "method": params.manifest()}
            if censoring.known:
                identity["analysis_window"] = censoring.run_id_component()
            result = {
                "mode": "multi_day_historical", "schema_version": "multi-day-1.0",
                "input_files": source_items, "bbox_lon_lat": list(bbox),
                "counts": counts, "events": diagnostics,
                "method_parameters": params.manifest(), "source_rights_status": "review_required",
                "analysis_window": censoring.summary(observed_range(first, last)),
                "limits": {"max_points": max_points, "max_scratch_mib": max_scratch_mib,
                           "max_export_mib": max_export_mib},
                "resources": {"scratch_peak_bytes": meter.peak_bytes,
                              "scratch_measurement": "sampled at commits; includes rollback journal"},
                "run_id": hashlib.sha256(
                    json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
                ).hexdigest(),
                "artifacts": {
                    name: {"sha256": checksum(path), "size_bytes": path.stat().st_size}
                    for name, path in files.items() if name != "manifest.json"
                },
                "warning": "Input file hashes are integrity evidence, not authenticated NOAA origin or validated vessel activity.",
            }
            files["manifest.json"].write_text(json.dumps(result, indent=2), encoding="utf-8")
            return result
        except Exception:
            for target in files.values():
                target.unlink(missing_ok=True)
            raise
        finally:
            db.close()


class _SQLiteGroupStore:
    """Group membership on disk, so a long candidate never sits in Python memory."""

    def __init__(self, db):
        self.db = db

    def add(self, group_id, ref, lon, lat):
        self.db.execute("INSERT INTO group_observations(group_id,observation_id) VALUES (?,?)",
                        (group_id, ref))

    def points(self, group_id):
        return ((lon, lat) for lat, lon in self.db.execute(
            "SELECT o.lat,o.lon FROM group_observations g "
            "JOIN observations o ON o.id=g.observation_id WHERE g.group_id=?", (group_id,)))


def _write_outputs(db, files, sources, params, export_cap_mib, censoring, meter):
    """Stream sorted observations through the shared engine and write exports."""
    max_bytes = export_cap_mib * 1048576
    # Both SQLite cursors and exports are sequential; there is no bulk
    # fetchall(), per-MMSI full track list, or growing array of events.
    with (files["houston_clean.csv"].open("w", newline="", encoding="utf-8") as clean,
          files["stationary_candidates.csv"].open("w", newline="", encoding="utf-8") as events,
          files["stationary_candidates.geojson"].open("w", encoding="utf-8") as geo):
        normalized = csv.DictWriter(clean, fieldnames=CLEAN_FIELDS, lineterminator="\n")
        normalized.writeheader()
        candidate_writer = csv.DictWriter(events, fieldnames=MULTIDAY_FIELDS, lineterminator="\n")
        candidate_writer.writeheader()
        geo.write('{"type":"FeatureCollection","harborlens_method":'
                  + json.dumps(geojson_method_member(params), separators=(",", ":"))
                  + ',"features":[\n')
        state = {"first": True, "cross_day": 0}

        def emit(record, group):
            seen_sources = [
                item[0] for item in db.execute(
                    "SELECT DISTINCT s.source_id FROM group_observations g "
                    "JOIN observation_sources s ON s.observation_id=g.observation_id "
                    "WHERE g.group_id=? ORDER BY s.source_id", (group["gid"],))
            ]
            refs = [sources[i]["source_ref"] for i in seen_sources]
            crossing = group["start_dt"].date() != group["end_dt"].date()
            record = {**record, "source_files_json": json.dumps(refs, separators=(",", ":")),
                      "source_count": len(refs), "crosses_utc_date": crossing}
            candidate_writer.writerow(record)
            properties = {k: v for k, v in record.items()
                          if k not in ("centroid_lon", "centroid_lat", "source_files_json")}
            properties["source_files"] = refs
            feature = {"type": "Feature",
                       "geometry": {"type": "Point",
                                    "coordinates": [record["centroid_lon"], record["centroid_lat"]]},
                       "properties": properties}
            if not state["first"]:
                geo.write(",\n")
            geo.write(json.dumps(feature, separators=(",", ":")))
            state["first"] = False
            state["cross_day"] += crossing

        engine = Segmenter(params, _SQLiteGroupStore(db), emit, censoring)
        cursor = db.execute(
            "SELECT id,mmsi,ts,lat,lon,sog,vessel_type,nav_status "
            "FROM observations ORDER BY mmsi,epoch_us,id"
        )
        for num_rows, (obs_id, mmsi, ts, lat, lon, sog, vessel_type, nav_status) in enumerate(cursor, 1):
            normalized.writerow({"mmsi": mmsi, "timestamp_utc": ts, "lat": lat, "lon": lon,
                                 "sog_knots": sog, "vessel_type": vessel_type, "nav_status": nav_status})
            if num_rows % 10000 == 0:
                clean.flush()
                if clean.tell() > max_bytes:
                    raise AISInputError("Multi-day cleaned CSV exceeded export byte cap")
                db.commit()
                meter.check()
            engine.feed(mmsi, datetime.fromisoformat(ts.replace("Z", "+00:00")),
                        lat, lon, sog, vessel_type, obs_id)
        stats = engine.close()
        stats["cross_day_candidates"] = state["cross_day"]
        geo.write("\n]}\n")
        for handle in (clean, events, geo):
            handle.flush()
            if handle.tell() > max_bytes:
                raise AISInputError("Multi-day export exceeds configured byte cap")
    return stats


def main():
    parser = argparse.ArgumentParser(description="Historical multi-day AIS stationary-candidate reconstruction")
    parser.add_argument("--input", nargs="+", required=True, type=Path, help="Two to seven local AIS subsets")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--bbox", nargs=4, type=float, default=BBOX_HOUSTON, metavar=("W","S","E","N"))
    parser.add_argument("--max-points", type=int, default=MAX_POINTS)
    parser.add_argument("--max-scratch-mib", type=int, default=MAX_SCRATCH_MIB)
    parser.add_argument("--max-export-mib", type=int, default=DEFAULT_EXPORT_MIB)
    parser.add_argument("--window-start", default=None,
                        help="One analysis window covering all inputs (ISO 8601 with Z); "
                             "only when inputs have no acquisition sidecars")
    parser.add_argument("--window-end", default=None)
    add_threshold_arguments(parser)
    args = parser.parse_args()
    result = run_multiday(
        args.input, args.out, bbox=tuple(args.bbox),
        max_points=args.max_points, max_scratch_mib=args.max_scratch_mib,
        max_export_mib=args.max_export_mib,
        window_start=args.window_start, window_end=args.window_end,
        params=params_from_args(args),
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
