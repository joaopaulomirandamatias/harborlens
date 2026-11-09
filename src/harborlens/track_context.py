"""SPEC-004: full observed-track versus polygon evidence, never port-event truth.

Reads existing cleaned AIS and stationary candidate outputs plus a local NOAA
polygon snapshot and its source receipt. No remote access, interpolation,
navigation guidance, berth assignment, waiting-time claim or event verification.
The output is a reproducible spatial *observation* report only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3
import tempfile
from collections import Counter
from datetime import timezone
from pathlib import Path

from harborlens.ais import parse_time
from harborlens.io_safe import AISInputError, stream_rows
from harborlens.provenance import checksum

MAX_CANDIDATES = 20000
MAX_AIS_POINTS = 1500000
MAX_OBSERVATIONS_PER_EVENT = 10000
MAX_GEOJSON_BYTES = 32 * 1048576
MAX_OUTPUT_BYTES = 48 * 1048576
MAX_SQLITE_MIB = 768
GAP_LIMIT_MINUTES = 15
MAX_CANDIDATE_SOG = 0.5
METHOD = "observed-track-polygon-v0.1"


class TrackEvidenceError(ValueError):
    """Invalid local inputs, missing provenance or unsupported evidence."""


def _json_document(path):
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_GEOJSON_BYTES:
        raise TrackEvidenceError("Missing, empty or oversized GeoJSON/provenance input")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise TrackEvidenceError("Invalid JSON input") from exc


def _epoch_microseconds(value):
    # Integer microseconds avoid ISO lexical-order errors at fractional seconds.
    t = parse_time(value).astimezone(timezone.utc)
    delta = t - t.fromtimestamp(0, tz=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds


def _load_zones(polygons):
    try:
        from shapely.geometry import Point, shape
        from shapely.strtree import STRtree
    except ImportError as exc:
        raise TrackEvidenceError("Install the geo extra: pip install 'harborlens[geo]'") from exc
    doc = _json_document(polygons)
    features = doc.get("features")
    if doc.get("type") != "FeatureCollection" or not isinstance(features, list) or not 1 <= len(features) <= 500:
        raise TrackEvidenceError("Expected a bounded nonempty polygon FeatureCollection")
    ids, geoms = [], []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise TrackEvidenceError("Malformed polygon feature")
        geom_data = feature.get("geometry") or {}
        if geom_data.get("type") not in ("Polygon", "MultiPolygon"):
            raise TrackEvidenceError("USACE point references are NOT polygon zones")
        props = feature.get("properties") or {}
        if props.get("historical_validity") != "not_verified":
            raise TrackEvidenceError("Only explicitly unverified historical polygon references are supported")
        try:
            geom = shape(geom_data)
        except Exception as exc:
            raise TrackEvidenceError("Invalid polygon geometry") from exc
        if geom.is_empty or not geom.is_valid or not geom.area > 0 or not all(math.isfinite(x) for x in geom.bounds):
            raise TrackEvidenceError("Degenerate, invalid or non-finite polygon")
        id_value = str(feature.get("id") or "")
        if not id_value or id_value in ids:
            raise TrackEvidenceError("Missing or duplicate polygon source id")
        ids.append(id_value)
        geoms.append(geom)
    return ids, geoms, STRtree(geoms), Point


def _source_receipt(polygons, explicit_receipt=None):
    path = Path(explicit_receipt) if explicit_receipt else Path(str(polygons) + ".source.json")
    receipt = _json_document(path)
    if receipt.get("output_sha256") != checksum(polygons):
        raise TrackEvidenceError("Polygon receipt/output SHA-256 mismatch")
    if receipt.get("historical_validity") != "not_verified" or receipt.get("geometry_review_status") != "unreviewed":
        raise TrackEvidenceError("Only unreviewed, historically unverified polygon receipts are supported")
    if receipt.get("rights_status") != "review_required":
        raise TrackEvidenceError("Source rights must remain review_required")
    return receipt, path


def _load_candidates(path):
    doc = _json_document(path)
    rows = doc.get("features")
    if doc.get("type") != "FeatureCollection" or not isinstance(rows, list) or len(rows) > MAX_CANDIDATES:
        raise TrackEvidenceError("Expected bounded candidate FeatureCollection")
    identifiers = set()
    for feature in rows:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise TrackEvidenceError("Invalid AIS candidate feature")
        if (feature.get("geometry") or {}).get("type") != "Point":
            raise TrackEvidenceError("Only POINT candidate centroids supported")
        props = feature.get("properties")
        if not isinstance(props, dict) or props.get("type") != "stationary_candidate" or props.get("confidence_label") != "unvalidated":
            raise TrackEvidenceError("Only explicitly unvalidated stationary candidates supported")
        identifier = props.get("event_id")
        if not isinstance(identifier, str) or not identifier or identifier in identifiers:
            raise TrackEvidenceError("Candidate event IDs must be unique")
        identifiers.add(identifier)
        mmsi = str(props.get("mmsi") or "")
        if not mmsi.isdigit() or len(mmsi) not in (8, 9):
            raise TrackEvidenceError("Invalid MMSI in candidate")
        try:
            start = _epoch_microseconds(props["start_utc"])
            end = _epoch_microseconds(props["end_utc"])
            expected = int(props["point_count"])
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise TrackEvidenceError("Invalid temporal candidate metadata") from exc
        if not (start < end and 1 <= expected <= MAX_OBSERVATIONS_PER_EVENT):
            raise TrackEvidenceError("Candidate duration or observation count outside limits")
    return rows


def _ingest_observations(path, database, max_points):
    required = {"mmsi", "timestamp_utc", "lat", "lon", "sog_knots"}
    count = invalid = 0
    reader = stream_rows(path)
    db = database
    cursor = db.cursor()
    for row in reader:
        count += 1
        if count > max_points:
            raise TrackEvidenceError("Cleaned AIS exceeds point cap; partial evidence forbidden")
        if not required.issubset(row):
            raise TrackEvidenceError("Cleaned AIS must have canonical columns")
        try:
            mmsi = str(row["mmsi"]).strip()
            epoch = _epoch_microseconds(row["timestamp_utc"])
            lat = float(row["lat"])
            lon = float(row["lon"])
            sog = float(row["sog_knots"])
            if not (mmsi.isdigit() and len(mmsi) in (8,9) and
                    all(map(math.isfinite, (lat, lon, sog))) and
                    -90 <= lat <= 90 and -180 <= lon <= 180 and 0 <= sog <= 100):
                raise ValueError("Bad numeric observation")
        except (TypeError, ValueError, KeyError, OverflowError):
            invalid += 1
            continue
        cursor.execute(
            "INSERT INTO ais(mmsi,epoch_us,lon,lat,sog) VALUES(?,?,?,?,?)",
            (mmsi,epoch,lon,lat,sog),
        )
        if count % 5000 == 0:
            db.commit()
    db.commit()
    if count == 0:
        raise TrackEvidenceError("Cleaned AIS is empty")
    return count, invalid


def _temporal_compatibility(props, receipt):
    # Explicit no-claims behavior. Even user-provided source dates do not
    # certify historical authority or make this an event classifier.
    start = _epoch_microseconds(props["start_utc"])
    end = _epoch_microseconds(props["end_utc"])
    from_date = receipt.get("effective_from_utc")
    to_date = receipt.get("effective_to_utc")
    if from_date is None and to_date is None:
        return "historical_validity_not_established"
    if from_date is not None and start < _epoch_microseconds(from_date):
        return "outside_declared_vintage"
    if to_date is not None and end >= _epoch_microseconds(to_date):
        return "outside_declared_vintage"
    return "inside_unreviewed_declared_vintage"


def _assess_one(db, feature, zones, geoms, tree, point_factory, receipt):
    p = feature["properties"]
    mmsi = str(p["mmsi"])
    start = _epoch_microseconds(p["start_utc"])
    end = _epoch_microseconds(p["end_utc"])
    expected = int(p["point_count"])
    query = db.execute(
        "SELECT epoch_us,lon,lat,sog FROM ais "
        "WHERE mmsi=? AND epoch_us>=? AND epoch_us<=? ORDER BY epoch_us,id "
        "LIMIT ?",
        (mmsi,start,end,MAX_OBSERVATIONS_PER_EVENT+1)
    )
    total = moving = max_gap = ambiguity = 0
    first = last = previous = None
    hits = Counter()
    for ts, lon, lat, sog in query:
        total += 1
        if total > MAX_OBSERVATIONS_PER_EVENT:
            break
        if first is None:
            first = ts
        if previous is not None:
            gap = (ts - previous) / 60000000
            max_gap = max(max_gap,gap)
        previous = last = ts
        moving += sog > MAX_CANDIDATE_SOG
        pt = point_factory(lon,lat)
        members = []
        for ix in tree.query(pt):
            index = int(ix)
            if geoms[index].covers(pt):
                members.append(zones[index])
        if len(members)>1:
            ambiguity += 1
        for match in members:
            hits[match] += 1
    complete = (
        total == expected and moving == 0 and first == start and last == end
        and max_gap <= GAP_LIMIT_MINUTES
    )
    if not complete:
        status = "incomplete_track_unknown"
    elif ambiguity or len(hits)>1:
        status = "multiple_zone_evidence_ambiguous"
    elif not hits:
        status = "no_observed_point_overlap"
    elif len(hits)==1 and next(iter(hits.values()))==total:
        status = "all_observed_points_within_one_polygon"
    else:
        status = "partial_observed_point_overlap"
    temporal = _temporal_compatibility(p, receipt)
    if temporal == "outside_declared_vintage":
        status = "outside_declared_vintage_unknown"
    counts = {k: hits[k] for k in sorted(hits)}
    return {
        "status":status,
        "observed_points":total,
        "candidate_expected_points":expected,
        "observation_count_matches":complete,
        "moving_points_in_window":moving,
        "max_observed_gap_minutes":round(max_gap,3),
        "points_in_multiple_polygons":ambiguity,
        "polygon_point_hits":counts,
        "source_polygon_ids":list(counts),
        "temporal_compatibility":temporal,
        "historical_validity":"not_verified",
        "operational_event_validation":"not_verified",
        "source_rights":"review_required",
        "method":METHOD,
        "warning":"Observed-track polygon context only; no validated anchorage, berth, waiting or port call.",
    }


def run_track_context(cleaned, candidates, polygons, out, polygon_receipt=None,
                      max_points=MAX_AIS_POINTS, scratch_mib=MAX_SQLITE_MIB):
    cleaned,candidates,polygons,out = map(Path,(cleaned,candidates,polygons,out))
    if out.suffix.lower() != ".geojson":
        raise TrackEvidenceError("Output must end in .geojson")
    sources = {x.resolve() for x in (cleaned,candidates,polygons)}
    sidecar = out.with_name(out.name + ".source.json")
    if out.resolve() in sources or sidecar.resolve() in sources or out.exists() or sidecar.exists():
        raise TrackEvidenceError("Refusing overwrite of inputs or existing output/receipt")
    if not (1 <= max_points <= MAX_AIS_POINTS and 16 <= scratch_mib <= MAX_SQLITE_MIB):
        raise TrackEvidenceError("Configured point/scratch limits exceeded")
    receipt, receipt_path = _source_receipt(polygons,polygon_receipt)
    features = _load_candidates(candidates)
    zone_ids, geoms, tree, point_factory = _load_zones(polygons)
    with tempfile.TemporaryDirectory(prefix="harborlens-track-") as work:
        db_path = Path(work)/"observations.sqlite"
        db=sqlite3.connect(db_path)
        try:
            db.execute("PRAGMA journal_mode=DELETE")
            db.execute("PRAGMA cache_size=-4096")
            db.execute("PRAGMA temp_store=FILE")
            db.execute("PRAGMA page_size=4096")
            db.execute(f"PRAGMA max_page_count={scratch_mib * 1048576 // 4096}")
            db.executescript(
                "CREATE TABLE ais (id INTEGER PRIMARY KEY,mmsi TEXT NOT NULL,"
                "epoch_us INTEGER NOT NULL,lon REAL NOT NULL,lat REAL NOT NULL,sog REAL NOT NULL);"
                "CREATE INDEX ix_mmsi_time ON ais(mmsi,epoch_us,id);"
            )
            rowcount, invalid = _ingest_observations(cleaned,db,max_points)
            if db_path.stat().st_size > scratch_mib * 1048576:
                raise TrackEvidenceError("SQLite scratch exceeded configured size")
            outcomes=Counter()
            result_features=[]
            for item in features:
                evidence=_assess_one(db,item,zone_ids,geoms,tree,point_factory,receipt)
                outcomes[evidence["status"]]+=1
                old=item["properties"]
                result_features.append({
                    "type":"Feature","geometry":item["geometry"],
                    "properties":{**old,"full_track_zone_evidence":evidence}
                })
            result={"type":"FeatureCollection","features":result_features}
            encoded=(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
            if len(encoded)>MAX_OUTPUT_BYTES:
                raise TrackEvidenceError("Output exceeds configured maximum size")
            summary={
                "schema_version":"full-track-context-v0.1",
                "method":METHOD,
                "inputs":{
                    "cleaned_ais_sha256":checksum(cleaned),
                    "candidate_geojson_sha256":checksum(candidates),
                    "polygon_geojson_sha256":checksum(polygons),
                    "polygon_receipt_sha256":checksum(receipt_path),
                },
                "output_sha256":hashlib.sha256(encoded).hexdigest(),
                "cleaned_rows_scanned":rowcount,
                "invalid_cleaned_rows":invalid,
                "candidate_count":len(features),
                "zone_polygon_count":len(zone_ids),
                "outcome_counts":dict(sorted(outcomes.items())),
                "polygon_source_retrieved_at_utc":receipt.get("retrieved_at_utc"),
                "historical_validity":"not_verified",
                "rights_status":"review_required",
                "warning":"All statuses describe unreviewed point overlap, not confirmed maritime events.",
            }
            out.parent.mkdir(parents=True,exist_ok=True)
            t=out.with_name(out.name+".partial")
            tmeta=sidecar.with_name(sidecar.name+".partial")
            try:
                with t.open("xb") as f:
                    f.write(encoded)
                with tmeta.open("x",encoding="utf-8") as f:
                    json.dump(summary,f,indent=2)
                t.replace(out)
                tmeta.replace(sidecar)
            except Exception:
                t.unlink(missing_ok=True)
                tmeta.unlink(missing_ok=True)
                out.unlink(missing_ok=True)
                raise
            return summary
        finally:
            db.close()


def main():
    p=argparse.ArgumentParser(description="Full observed AIS track/polygon evidence — NOT verified port events")
    p.add_argument("--cleaned",type=Path,required=True,help="Canonical cleaned AIS CSV")
    p.add_argument("--candidates",type=Path,required=True,help="Stationary candidates GeoJSON")
    p.add_argument("--polygons",type=Path,required=True,help="NOAA Polygon GeoJSON")
    p.add_argument("--polygon-receipt",type=Path,default=None,help="Source SHA-256 receipt; default adjacent .source.json")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--max-points",type=int,default=MAX_AIS_POINTS)
    p.add_argument("--scratch-mib",type=int,default=MAX_SQLITE_MIB)
    a=p.parse_args()
    print(json.dumps(run_track_context(a.cleaned,a.candidates,a.polygons,a.out,
                                      a.polygon_receipt,a.max_points,a.scratch_mib),indent=2))


if __name__=="__main__":
    main()
