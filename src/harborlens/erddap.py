"""Opt-in NOAA PMEL ERDDAP AIS2024 geographically bounded CSV acquisition.

No network calls on install or standard HarborLens analysis. A successful
download does not verify source authenticity, vessel activity or reuse rights.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from harborlens.rights import PURPOSES, rights_receipt
from harborlens.timeparse import ExplicitOffsetRequired, parse_explicit_utc

BASE = "https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.csv"
INFO = "https://data.pmel.noaa.gov/pmel/erddap/info/AIS2024_AIS/index.html"
FIELDS = ("MMSI", "time", "Lat", "Lon", "SOG", "VesselType", "Status")
HOUSTON = (-95.70, 29.10, -94.20, 30.10)


class AcquisitionError(ValueError):
    """Requested geographic subset or source response was not usable."""


def utc(value: str) -> datetime:
    """Parse a query bound. Uppercase ``T``, required ``Z`` or ``±HH:MM``, no strip.

    The fraction is absent or 1 to 6 digits. A non-UTC offset is converted
    to UTC. A space separator and a naive clock are rejected.
    """
    try:
        return parse_explicit_utc(value)
    except ExplicitOffsetRequired as exc:
        raise AcquisitionError("Datetime requires timezone offset or Z") from exc
    except (TypeError, ValueError) as exc:
        raise AcquisitionError("Invalid ISO8601 UTC datetime") from exc


def build_url(start: str, end: str, bbox=HOUSTON) -> str:
    beginning, ending = utc(start), utc(end)
    if beginning.year != 2024 or ending.year != 2024 or not beginning < ending:
        raise AcquisitionError("A positive time window within 2024 is required")
    if ending - beginning > timedelta(hours=6):
        raise AcquisitionError("A query may cover at most six hours")
    if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
        raise AcquisitionError("Expected four finite bounding box values")
    w, s, e, n = map(float, bbox)
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise AcquisitionError("Invalid west/south/east/north bounding box")
    fmt = lambda value: value.strftime("%Y-%m-%dT%H:%M:%SZ")
    clauses = (
        f"time>={fmt(beginning)}", f"time<={fmt(ending)}",
        f"Lat>={s:g}", f"Lat<={n:g}", f"Lon>={w:g}", f"Lon<={e:g}",
    )
    return BASE + "?" + ",".join(FIELDS) + "&" + "&".join(
        quote(clause, safe="=,:-") for clause in clauses
    )


def download_bytes(response, cap: int) -> bytes:
    declared = getattr(response, "headers", {}).get("Content-Length")
    if declared is not None and int(declared) > cap:
        raise AcquisitionError("Response exceeds configured byte cap")
    chunks = []
    total = 0
    while True:
        block = response.read(min(65536, cap - total + 1))
        if not block:
            break
        total += len(block)
        if total > cap:
            raise AcquisitionError("Response exceeds configured byte cap")
        chunks.append(block)
    return b"".join(chunks)


def normalize_response(raw: bytes) -> tuple[bytes, int]:
    try:
        rows = csv.reader(io.StringIO(raw.decode("utf-8-sig")))
        header = next(rows)
    except (UnicodeError, csv.Error, StopIteration) as exc:
        raise AcquisitionError("Invalid CSV response from data service") from exc
    if tuple(header) != FIELDS:
        raise AcquisitionError("Unexpected NOAA CSV header; service may have returned an error")
    result = io.StringIO(newline="")
    writer = csv.writer(result, lineterminator="\n")
    writer.writerow(header)
    count = 0
    try:
        for row in rows:
            if count == 0 and len(row) == len(FIELDS) and row[1] == "UTC":
                continue  # ERDDAP .csv units line
            if len(row) != len(FIELDS):
                raise AcquisitionError("Unexpected column count in NOAA row")
            writer.writerow(row)
            count += 1
    except csv.Error as exc:
        raise AcquisitionError("Malformed CSV response") from exc
    if count == 0:
        raise AcquisitionError("NOAA returned no observations for this subset")
    return result.getvalue().encode("utf-8"), count


def fetch_subset(start, end, bbox, output, max_mib=8, opener=None,
                 rights_register=None, rights_purpose="research"):
    """Explicit, testable network operation. No remote access in unit tests."""
    output = Path(output)
    metadata = output.with_name(output.name + ".source.json")
    if output.suffix != ".csv" or not (1 <= max_mib <= 64):
        raise AcquisitionError("Output must be .csv and max_mib within 1..64")
    url = build_url(start, end, bbox)
    if output.exists() or metadata.exists():
        raise FileExistsError("Refusing overwrite of existing AIS file or metadata")
    rights = rights_receipt("noaa_pmel_erddap", dataset_version="AIS2024_AIS",
                            purpose=rights_purpose, register_path=rights_register)
    request = Request(url, headers={"User-Agent": "HarborLens-research/0.1", "Accept": "text/csv"})
    with (opener or urlopen)(request, timeout=45) as response:
        raw = download_bytes(response, max_mib * 1048576)
    normalized, count = normalize_response(raw)
    report = {
        "agency": "NOAA/OAR/PMEL", "dataset": "AIS2024_AIS",
        "dataset_metadata": INFO, "source_url": url,
        "time_start_utc": utc(start).isoformat().replace("+00:00", "Z"),
        "time_end_utc": utc(end).isoformat().replace("+00:00", "Z"),
        "bbox_lon_lat": list(map(float, bbox)),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "csv_sha256": hashlib.sha256(normalized).hexdigest(),
        "response_bytes": len(raw), "rows": count,
        "rights_status": rights["rights_status"],
        "rights_review": rights,
        "warning": "Historical AIS, not verified port events; review origin and reuse rights.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".partial")
    tmp_meta = metadata.with_name(metadata.name + ".partial")
    try:
        with tmp.open("xb") as handle:
            handle.write(normalized)
        with tmp_meta.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        os.replace(tmp, output)
        os.replace(tmp_meta, metadata)
    except Exception:
        tmp.unlink(missing_ok=True)
        tmp_meta.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description="Fetch a bounded historical NOAA PMEL AIS2024 subset")
    parser.add_argument("--start", required=True,
                        help="YYYY-MM-DDTHH:MM:SSZ or ±HH:MM; 0-6 fraction digits; no surrounding space")
    parser.add_argument("--end", required=True,
                        help="Same grammar as --start, and later than --start within 2024")
    parser.add_argument("--bbox", nargs=4, type=float, default=HOUSTON, metavar=("W", "S", "E", "N"))
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--max-mib", type=int, default=8)
    parser.add_argument("--rights-register", type=Path, default=None)
    parser.add_argument("--rights-purpose", choices=PURPOSES, default="research")
    args = parser.parse_args()
    print(json.dumps(fetch_subset(args.start, args.end, args.bbox, args.out, args.max_mib,
                                  rights_register=args.rights_register,
                                  rights_purpose=args.rights_purpose), indent=2))


if __name__ == "__main__":
    main()
