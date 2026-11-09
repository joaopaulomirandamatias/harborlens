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
from datetime import datetime
from pathlib import Path

from harborlens.ais import (
    BBOX_HOUSTON, CLEAN_FIELDS, EVENT_FIELDS, header_alias,
    haversine_m, parse_time, sha256,
)
from harborlens.io_safe import AISInputError, stream_rows
from harborlens.provenance import checksum, FILES

METHOD = "stationary-multiday-v0.1"
MULTIDAY_FIELDS = EVENT_FIELDS + ["source_files_json", "source_count", "crosses_utc_date"]
MAX_FILES = 7
MAX_POINTS = 1_500_000
MAX_SCRATCH_MIB = 1024
MAX_EXPORT_MIB = 512
KNOTS_TO_MPS = 0.514444


def _csv_bytes(fields):
    stream = io.StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerow(fields)
    return stream.getvalue().encode("utf-8")


def _utc(value):
    return parse_time(value).isoformat().replace("+00:00", "Z")


def _enforce_scratch_limit(db_path, cap_bytes):
    # The scratch database is deleted even on failure. Include journal bytes.
    size = db_path.stat().st_size if db_path.exists() else 0
    journal = db_path.with_name(db_path.name + "-journal")
    if journal.exists():
        size += journal.stat().st_size
    if size > cap_bytes:
        raise AISInputError("Multi-day SQLite scratch store exceeded configured disk cap")


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


def _load_files(db, inputs, bbox, max_points, db_path, max_scratch_mib):
    counts = {
        "total": 0, "invalid": 0, "outside_bbox": 0, "duplicate": 0,
        "duplicate_across_files": 0, "written": 0,
    }
    source_items = []
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
                timestamp = _utc(row[columns["timestamp"]])
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
                   (mmsi,ts,lat,lon,sog,vessel_type,nav_status,lat_micro,lon_micro)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (mmsi, timestamp, lat, lon, sog, vessel_type, nav_status, key[2], key[3]),
            )
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
                _enforce_scratch_limit(db_path, max_scratch_mib * 1048576)
        if file_rows == 0:
            raise AISInputError(f"Source has no AIS observations: {path.name}")
        item["rows_scanned"] = file_rows
        db.commit()
        _enforce_scratch_limit(db_path, max_scratch_mib * 1048576)
    return counts, source_items


def _output_files(out):
    return {name: out / name for name in (*FILES, "manifest.json")}


def run_multiday(
    inputs,
    out,
    bbox=BBOX_HOUSTON,
    max_points=MAX_POINTS,
    max_scratch_mib=MAX_SCRATCH_MIB,
    max_export_mib=256,
    max_sog=0.5,
    min_duration_minutes=30,
    max_gap_minutes=15,
    max_radius_m=1000,
    min_points=8,
    max_jump_knots=65,
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
    if not (max_sog >= 0 and min_duration_minutes > 0 and max_gap_minutes > 0
            and max_radius_m > 0 and min_points >= 2 and max_jump_knots > 0):
        raise AISInputError("Invalid inference parameters")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    files = _output_files(out)
    if any(path in paths or path.exists() for path in files.values()):
        raise FileExistsError("Output files already exist or would overwrite a source")

    # Use a private ephemeral scratch directory; never commit or upload AIS.
    with tempfile.TemporaryDirectory(prefix="harborlens-scratch-") as folder:
        db_path = Path(folder) / "ais.sqlite3"
        db = _make_db(db_path, max_scratch_mib)
        try:
            counts, source_items = _load_files(
                db, paths, tuple(bbox), max_points, db_path, max_scratch_mib
            )
            db.commit()
            diagnostics = {
                "vessels": 0, "points": counts["written"], "stationary_candidates": 0,
                "cross_day_candidates": 0, "moving_points": 0,
                "gap_splits": 0, "identity_conflicts": 0,
                "implausible_jumps": 0, "timestamp_conflicts": 0,
                "spatial_splits": 0, "discarded_groups": 0,
                "warning": "Only unvalidated stationary candidates, not confirmed berths or waiting vessels.",
            }
            params = {
                "method_version": METHOD, "max_sog_knots": max_sog,
                "min_duration_minutes": min_duration_minutes,
                "max_gap_minutes": max_gap_minutes, "max_radius_m": max_radius_m,
                "min_points": min_points, "max_jump_knots": max_jump_knots,
            }
            _write_outputs(db, files, source_items, diagnostics, params, max_export_mib)
            result = {
                "mode": "multi_day_historical", "schema_version": "multi-day-1.0",
                "input_files": source_items, "bbox_lon_lat": list(bbox),
                "counts": counts, "events": diagnostics,
                "method_parameters": params, "source_rights_status": "review_required",
                "run_id": hashlib.sha256(
                    json.dumps(
                        {"source_hashes": sorted(x["sha256"] for x in source_items),
                         "bbox": list(bbox), "method": params},
                        sort_keys=True, separators=(",", ":")
                    ).encode("utf-8")
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


def _write_outputs(db, files, sources, stats, params, export_cap_mib):
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
        geo.write('{"type":"FeatureCollection","features":[\n')
        stats["vessels"] = db.execute("SELECT count(DISTINCT mmsi) FROM observations").fetchone()[0]
        cursor = db.execute(
            "SELECT id,mmsi,ts,lat,lon,sog,vessel_type,nav_status "
            "FROM observations ORDER BY mmsi,ts,id"
        )
        current = None
        group_id = 0
        first_feature = True
        last_mmsi = None
        num_rows = 0

        def finish_group():
            nonlocal current, first_feature
            if current is None:
                return
            group = current
            current = None
            if group["count"] < params["min_points"]:
                stats["discarded_groups"] += 1
                return
            span = (group["end_dt"] - group["start_dt"]).total_seconds() / 60
            if span < params["min_duration_minutes"]:
                stats["discarded_groups"] += 1
                return
            center = (group["sum_lon"] / group["count"], group["sum_lat"] / group["count"])
            distances = (
                haversine_m(center, (lon, lat))
                for lat, lon in db.execute(
                    "SELECT o.lat,o.lon FROM group_observations g "
                    "JOIN observations o ON o.id=g.observation_id WHERE g.group_id=?",
                    (group["gid"],)
                )
            )
            max_distance = max(distances, default=0)
            if max_distance > params["max_radius_m"]:
                stats["discarded_groups"] += 1
                return
            seen_sources = [
                item[0] for item in db.execute(
                    "SELECT DISTINCT s.source_id FROM group_observations g "
                    "JOIN observation_sources s ON s.observation_id=g.observation_id "
                    "WHERE g.group_id=? ORDER BY s.source_id",
                    (group["gid"],)
                )
            ]
            refs = [sources[i]["source_ref"] for i in seen_sources]
            start = group["start_dt"].isoformat().replace("+00:00", "Z")
            end = group["end_dt"].isoformat().replace("+00:00", "Z")
            eid = hashlib.sha256(f"{group['mmsi']}|{start}|{end}|{METHOD}".encode()).hexdigest()[:18]
            crossing = group["start_dt"].date() != group["end_dt"].date()
            record = {
                "event_id": eid, "mmsi": group["mmsi"],
                "start_utc": start, "end_utc": end, "duration_min": round(span, 2),
                "point_count": group["count"], "centroid_lon": round(center[0], 6),
                "centroid_lat": round(center[1], 6),
                "maximum_distance_m": round(max_distance, 1),
                "type": "stationary_candidate", "method_version": METHOD,
                "confidence_label": "unvalidated",
                "source_files_json": json.dumps(refs, separators=(",", ":")),
                "source_count": len(refs), "crosses_utc_date": crossing,
            }
            candidate_writer.writerow(record)
            properties = {k: v for k, v in record.items() if k not in ("centroid_lon", "centroid_lat")}
            properties["source_files"] = refs
            properties.pop("source_files_json")
            feature = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [record["centroid_lon"], record["centroid_lat"]]},
                "properties": properties,
            }
            if not first_feature:
                geo.write(",\n")
            geo.write(json.dumps(feature, separators=(",", ":")))
            first_feature = False
            stats["stationary_candidates"] += 1
            if crossing:
                stats["cross_day_candidates"] += 1

        def reset_group(obs_id, mmsi, time, lat, lon, vessel_type):
            nonlocal current, group_id
            group_id += 1
            current = {
                "gid": group_id, "mmsi": mmsi,
                "start_dt": time, "end_dt": time,
                "first": (lon, lat), "last": (lon, lat),
                "sum_lat": 0.0, "sum_lon": 0.0, "count": 0,
                "vessel_type": vessel_type,
            }

        for obs_id, mmsi, ts, lat, lon, sog, vessel_type, nav_status in cursor:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            normalized.writerow({
                "mmsi": mmsi, "timestamp_utc": ts, "lat": lat, "lon": lon,
                "sog_knots": sog, "vessel_type": vessel_type,
                "nav_status": nav_status,
            })
            num_rows += 1
            if num_rows % 10000 == 0:
                clean.flush()
                if clean.tell() > max_bytes:
                    raise AISInputError("Multi-day cleaned CSV exceeded export byte cap")
                _enforce_scratch_limit(Path(db.execute("PRAGMA database_list").fetchone()[2]), max_bytes * 4)

            if last_mmsi is not None and mmsi != last_mmsi:
                finish_group()
            last_mmsi = mmsi
            if sog > params["max_sog_knots"]:
                stats["moving_points"] += 1
                finish_group()
                continue
            if current is not None:
                gap = (dt - current["end_dt"]).total_seconds() / 60.0
                velocity = haversine_m(current["last"], (lon, lat)) / max(gap * 60, 0.001) / KNOTS_TO_MPS
                reason = None
                if gap <= 0:
                    reason = "timestamp_conflicts"
                elif gap > params["max_gap_minutes"]:
                    reason = "gap_splits"
                elif current["vessel_type"] and vessel_type and vessel_type != current["vessel_type"]:
                    reason = "identity_conflicts"
                elif velocity > params["max_jump_knots"]:
                    reason = "implausible_jumps"
                elif haversine_m(current["first"], (lon, lat)) > 2 * params["max_radius_m"]:
                    reason = "spatial_splits"
                if reason:
                    stats[reason] += 1
                    finish_group()
            if current is None:
                reset_group(obs_id, mmsi, dt, lat, lon, vessel_type)
            group = current
            group["end_dt"] = dt
            group["last"] = (lon, lat)
            group["sum_lat"] += lat
            group["sum_lon"] += lon
            group["count"] += 1
            if not group["vessel_type"] and vessel_type:
                group["vessel_type"] = vessel_type
            db.execute(
                "INSERT INTO group_observations(group_id,observation_id) VALUES (?,?)",
                (group["gid"], obs_id),
            )
        finish_group()
        geo.write("\n]}\n")
        for handle in (clean, events, geo):
            handle.flush()
            if handle.tell() > max_bytes:
                raise AISInputError("Multi-day export exceeds configured byte cap")


def main():
    parser = argparse.ArgumentParser(description="Historical multi-day AIS stationary-candidate reconstruction")
    parser.add_argument("--input", nargs="+", required=True, type=Path, help="Two to seven local AIS subsets")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--bbox", nargs=4, type=float, default=BBOX_HOUSTON, metavar=("W","S","E","N"))
    parser.add_argument("--max-points", type=int, default=MAX_POINTS)
    parser.add_argument("--max-scratch-mib", type=int, default=MAX_SCRATCH_MIB)
    parser.add_argument("--max-export-mib", type=int, default=256)
    args = parser.parse_args()
    result = run_multiday(
        args.input, args.out, bbox=tuple(args.bbox),
        max_points=args.max_points, max_scratch_mib=args.max_scratch_mib,
        max_export_mib=args.max_export_mib,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
