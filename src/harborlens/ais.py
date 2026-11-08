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
import statistics
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from harborlens.io_safe import stream_rows, AISInputError
from harborlens.provenance import add_provenance

BBOX_HOUSTON = (-95.70, 29.10, -94.20, 30.10)  # west, south, east, north
ALIASES = {
    "mmsi": ("MMSI","mmsi"),
    "timestamp": ("BaseDateTime","BASE_DATE_TIME","time"),
    "lat": ("LAT","Lat","latitude"),
    "lon": ("LON","Lon","longitude"),
    "sog": ("SOG","sog"),
    "vessel_type": ("VesselType","vessel_type"),
    "nav_status": ("Status","nav_status","NavigationStatus"),
}
CLEAN_FIELDS = ["mmsi","timestamp_utc","lat","lon","sog_knots","vessel_type","nav_status"]
EVENT_FIELDS = ["event_id","mmsi","start_utc","end_utc","duration_min","point_count",
                "centroid_lon","centroid_lat","maximum_distance_m","type","method_version","confidence_label"]

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
    with output.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=CLEAN_FIELDS)
        writer.writeheader()
        cols=None
        for row in stream_rows(source):
            if cols is None:
                cols={k:header_alias(list(row),k,k not in ("vessel_type","nav_status")) for k in ALIASES}
            if max_rows is not None and counts["total"]>=max_rows:
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
            writer.writerow({
                "mmsi":mmsi,"timestamp_utc":t.isoformat().replace("+00:00","Z"),
                "lat":lat,"lon":lon,"sog_knots":sog,
                "vessel_type":row.get(cols["vessel_type"],"") if cols["vessel_type"] else "",
                "nav_status":row.get(cols["nav_status"],"") if cols["nav_status"] else "",
            })
            counts["written"]+=1
    return {"input_file":str(source),"input_sha256":sha256(source),"output":str(output),
            "bbox_lon_lat":list(bbox),"counts":counts,"note":"QA counts, not port-call statistics"}

def haversine_m(a,b):
    lon1,lat1=a
    lon2,lat2=b
    r=6371008.8
    phi1,phi2=math.radians(lat1),math.radians(lat2)
    dphi=phi2-phi1
    dlambda=math.radians(lon2-lon1)
    x=math.sin(dphi/2)**2+math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2*r*math.asin(min(1,math.sqrt(x)))

def infer_candidates(cleaned, max_sog=0.5, min_duration_minutes=30,
                     max_gap_minutes=15, max_radius_m=1000, min_points=8):
    by_mmsi=defaultdict(list)
    with cleaned.open("r",newline="",encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            try:
                row["dt"]=parse_time(row["timestamp_utc"])
                row["lon"]=float(row["lon"])
                row["lat"]=float(row["lat"])
                row["sog_knots"]=float(row["sog_knots"])
            except (ValueError,TypeError,KeyError):
                continue
            by_mmsi[row["mmsi"]].append(row)
    events=[]
    stats={"vessels":len(by_mmsi),"points":sum(len(x) for x in by_mmsi.values()),"moving_or_invalid_points":0}
    for mmsi, rows in by_mmsi.items():
        rows.sort(key=lambda row:row["dt"])
        group=[]
        def finish():
            if len(group)<min_points:
                return
            duration=(group[-1]["dt"]-group[0]["dt"]).total_seconds()/60
            if duration<min_duration_minutes:
                return
            center=(statistics.mean(x["lon"] for x in group),statistics.mean(x["lat"] for x in group))
            max_dist=max(haversine_m(center,(x["lon"],x["lat"])) for x in group)
            if max_dist>max_radius_m:
                return
            start=group[0]["dt"].isoformat().replace("+00:00","Z")
            end=group[-1]["dt"].isoformat().replace("+00:00","Z")
            uid=hashlib.sha256(f"{mmsi}|{start}|{end}|stationary-v0.1".encode()).hexdigest()[:18]
            events.append({
                "event_id":uid,"mmsi":mmsi,"start_utc":start,"end_utc":end,
                "duration_min":round(duration,2),"point_count":len(group),
                "centroid_lon":round(center[0],6),"centroid_lat":round(center[1],6),
                "maximum_distance_m":round(max_dist,1),"type":"stationary_candidate",
                "method_version":"stationary-v0.1","confidence_label":"unvalidated"})
        for row in rows:
            if row["sog_knots"]>max_sog:
                stats["moving_or_invalid_points"]+=1
                finish()
                group=[]
                continue
            if group:
                gap=(row["dt"]-group[-1]["dt"]).total_seconds()/60
                far=haversine_m((row["lon"],row["lat"]),(group[0]["lon"],group[0]["lat"]))
                if gap>max_gap_minutes or gap<=0 or far>max_radius_m*2:
                    finish()
                    group=[]
            group.append(row)
        finish()
    stats["stationary_candidates"]=len(events)
    stats["warning"]="Stationary candidates are unvalidated, NOT verified berth, anchorage, waiting, or port calls."
    return events,stats

def write_events(events,out):
    out.mkdir(parents=True,exist_ok=True)
    with (out/"stationary_candidates.csv").open("w",newline="",encoding="utf-8") as stream:
        writer=csv.DictWriter(stream,fieldnames=EVENT_FIELDS)
        writer.writeheader()
        writer.writerows(events)
    features=[{"type":"Feature","geometry":{"type":"Point","coordinates":[e["centroid_lon"],e["centroid_lat"]]},
               "properties":{k:v for k,v in e.items() if k not in ("centroid_lon","centroid_lat")}} for e in events]
    (out/"stationary_candidates.geojson").write_text(json.dumps({"type":"FeatureCollection","features":features},indent=2),encoding="utf-8")

def run(src,out,bbox=BBOX_HOUSTON,max_rows=None,source_url=None):
    out.mkdir(parents=True,exist_ok=True)
    cleaned=out/"houston_clean.csv"
    manifest=ingest(src,cleaned,bbox,max_rows)
    events,stats=infer_candidates(cleaned)
    write_events(events,out)
    manifest["events"]=stats
    manifest["method_parameters"]={"max_sog_knots":0.5,"min_duration_minutes":30,
                                   "max_gap_minutes":15,"max_radius_m":1000,"min_points":8}
    manifest = add_provenance(out, manifest, source_url=source_url)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest
