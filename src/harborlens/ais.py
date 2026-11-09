"""NOAA-style historical AIS processing with unvalidated stationary candidates.

Experimental research only. Do NOT use for navigation, vessel control,
live traffic management, port-call truth, or certified emissions estimates.
"""
from __future__ import annotations
import csv
import gzip
import hashlib
import io
import json
import math
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from harborlens.io_safe import stream_rows, AISInputError
from harborlens.provenance import add_provenance
from harborlens.censoring import (
    WindowCensoring, declaration_record, observed_range, parse_utc, resolve_input_window,
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
# New columns are appended so positional consumers of earlier files keep working (#39).
CLEAN_FIELDS = ["mmsi","timestamp_utc","lat","lon","sog_knots","vessel_type","nav_status",
                "cog_deg","heading_deg","length_m","width_m","draft_m","transceiver_class","mmsi_category"]
EVENT_FIELDS = ["event_id","mmsi","start_utc","end_utc","duration_min","point_count",
                "centroid_lon","centroid_lat","maximum_distance_m","type","method_version","parameter_set",
                "confidence_label","left_censoring","right_censoring",
                "vessel_type","transceiver_class","length_m","draft_m","mmsi_category"]

def header_alias(header, name, required=True):
    indexed={x.lower().strip():x for x in header}
    for candidate in ALIASES[name]:
        if candidate.lower() in indexed:
            return indexed[candidate.lower()]
    if required:
        raise ValueError(f"Missing {name} in CSV columns: {header}")
    return None

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(8*1024*1024),b""):
            h.update(block)
    return h.hexdigest()

def parse_time(value):
    t=datetime.fromisoformat(str(value).strip().replace("Z","+00:00").replace(" ","T"))
    if t.tzinfo is None:
        t=t.replace(tzinfo=timezone.utc)  # NOAA BaseDateTime convention
    return t.astimezone(timezone.utc)

def ingest(source, output, bbox=BBOX_HOUSTON, max_rows=None):
    if max_rows is not None and max_rows < 0:
        raise AISInputError("max_rows must not be negative")
    if len(bbox) != 4 or not all(math.isfinite(float(x)) for x in bbox):
        raise AISInputError("Bounding box must have four finite numbers")
    if not (-180 <= bbox[0] < bbox[2] <= 180 and -90 <= bbox[1] < bbox[3] <= 90):
        raise AISInputError("Bounding box must be ordered west,south,east,north")
    if source.resolve() == output.resolve():
        raise AISInputError("Input and output paths must be different")
    output.parent.mkdir(parents=True,exist_ok=True)
    counts=dict(total=0,in_bbox=0,invalid=0,outside_bbox=0,duplicate=0,written=0)
    seen=set()
    first=last=None
    truncated=False
    categories={}
    with output.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=CLEAN_FIELDS)
        writer.writeheader()
        cols=None
        for row in stream_rows(source):
            if cols is None:
                cols={k:header_alias(list(row),k,k not in OPTIONAL_COLUMNS) for k in ALIASES}
            if max_rows is not None and counts["total"]>=max_rows:
                truncated=True
                break
            counts["total"]+=1
            try:
                mmsi=str(row[cols["mmsi"]]).strip()
                t=parse_time(row[cols["timestamp"]])
                lat=float(row[cols["lat"]])
                lon=float(row[cols["lon"]])
                sog=float(row[cols["sog"]])
                if not mmsi.isdigit() or len(mmsi) not in (8,9):
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
                "vessel_type":get("vessel_type"),"nav_status":get("nav_status"),
                **{k:csv_value(v) for k,v in attributes.items()},"mmsi_category":category,
            })
            counts["written"]+=1
            first=t if first is None or t<first else first
            last=t if last is None or t>last else last
    return {"input_file":str(source),"input_sha256":sha256(source),"output":str(output),
            "bbox_lon_lat":list(bbox),"counts":counts,"note":"QA counts, not port-call statistics",
            "input_truncated":truncated,"limits":{"max_rows":max_rows},
            "mmsi_categories":dict(sorted(categories.items())),
            "observed_time_range":observed_range(first,last)}

# Kept for callers that import it from this module; the engine owns the implementation.
haversine_m = _haversine_m

# In-memory consumers hold ~470 bytes per cleaned row (measured on 3.9 million rows:
# ~1.8 GiB RSS). The cap bounds memory at roughly 2.8 GiB and fails before loading more.
MAX_IN_MEMORY_ROWS = 6_000_000

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
                rows.append((str(row["mmsi"]),parse_time(row["timestamp_utc"]),float(row["lat"]),
                             float(row["lon"]),float(row["sog_knots"]),str(row.get("vessel_type") or ""),index,
                             parse_csv_attributes(row)))
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
            if k in CANDIDATE_CSV_OPTIONAL:
                return CANDIDATE_CSV_OPTIONAL[k](v) if v!="" else None
            return CANDIDATE_CSV_TYPES[k](v) if k in CANDIDATE_CSV_TYPES else v
        return [{k:convert(k,v) for k,v in row.items() if k in EVENT_FIELDS}
                for row in csv.DictReader(stream)]

def write_events(events,out,params=None):
    params=params or SegmentationParams()
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stationary_candidates.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    features=[{"type":"Feature","geometry":{"type":"Point","coordinates":[e["centroid_lon"],e["centroid_lat"]]},
               "properties":{k:v for k,v in e.items() if k not in ("centroid_lon","centroid_lat")}} for e in events]
    collection={"type":"FeatureCollection","harborlens_method":geojson_method_member(params),"features":features}
    (out/"stationary_candidates.geojson").write_text(json.dumps(collection,indent=2),encoding="utf-8")

def run(src,out,bbox=BBOX_HOUSTON,max_rows=None,source_url=None,window_start=None,window_end=None,
        params=None):
    """Ingest one AIS file, infer candidates and write a provenance manifest.

    The analysis window comes from ``window_start``/``window_end`` or from a
    verified acquisition sidecar next to ``src``. A run truncated by
    ``max_rows`` reports censoring as unknown, because its effective end is unknown.
    ``params`` (SegmentationParams) defaults to the documented BR-003 thresholds.
    """
    params=params or SegmentationParams()
    src=Path(src)
    out.mkdir(parents=True,exist_ok=True)
    cleaned=out/"houston_clean.csv"
    manifest=ingest(src,cleaned,bbox,max_rows)
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
    write_events(events,out,params)
    manifest["events"]=stats
    manifest["method_parameters"]=params.manifest()
    manifest["analysis_window"]=censoring.summary(observed)
    manifest = add_provenance(out, manifest, source_url=source_url)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest
