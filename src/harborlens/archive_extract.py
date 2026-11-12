"""Bounded geographic/time extraction from a local NOAA daily .csv.zst archive.

The caller supplies an already downloaded daily archive. The algorithm scans
the complete stream before declaring a complete subset; no silent truncation.
It does not determine berth, anchorage, waiting, or validated port calls.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from contextlib import contextmanager
from pathlib import Path

from harborlens.ais import BBOX_HOUSTON, header_alias, parse_time, sha256
from harborlens.timeparse import ExplicitOffsetRequired, parse_explicit_utc
from harborlens.io_safe import LimitedReader, MAX_COMPRESSED_BYTES, AISInputError, _open_text_stream
from harborlens.vintages import header_style, vintage_for
from harborlens.rights import PURPOSES, rights_receipt

MAX_UNCOMPRESSED_GIB = 8
# One full UTC day in the Houston research rectangle is ~560,000 rows (~105 bytes
# each, ~59 MiB). Ceilings leave headroom for busier days and still fail closed.
MAX_OUTPUT_MIB = 256
MAX_MATCHING_ROWS = 1_000_000
DEFAULT_OUTPUT_MIB = 128


def utc(value):
    """Parse an extraction bound. Uppercase ``T``, required ``Z`` or ``±HH:MM``, no strip.

    The fraction is absent or 1 to 6 digits. A non-UTC offset is converted
    to UTC. A space separator and a naive clock are rejected.
    """
    try:
        return parse_explicit_utc(value)
    except ExplicitOffsetRequired as exc:
        raise AISInputError("UTC time with offset or Z required") from exc
    except (TypeError, ValueError) as exc:
        raise AISInputError("Use an ISO8601 date/time with timezone") from exc


def _csv_row_bytes(row):
    buffer = io.StringIO(newline="")
    csv.writer(buffer, lineterminator="\n").writerow(row)
    return buffer.getvalue().encode("utf-8")


@contextmanager
def _archive_text(source, max_uncompressed_gib):
    """Text stream over a daily archive: zstd (2024+) or single-CSV ZIP (2015-2023)."""
    if source.name.lower().endswith(".zip"):
        # Bounded ZIP reader: one CSV member, expansion-ratio and size caps (io_safe).
        with _open_text_stream(source) as text:
            yield text
        return
    try:
        import zstandard
    except ImportError as exc:
        raise AISInputError("Install optional dependency: pip install 'harborlens[noaa]'") from exc
    with source.open("rb") as binary:
        with zstandard.ZstdDecompressor().stream_reader(binary) as decoder:
            with io.TextIOWrapper(
                io.BufferedReader(LimitedReader(decoder, max_uncompressed_gib * (1024 ** 3))),
                encoding="utf-8-sig", newline=""
            ) as text:
                yield text


def extract_archive(
    source, output, start, end, bbox=BBOX_HOUSTON,
    max_rows=MAX_MATCHING_ROWS, max_output_mib=DEFAULT_OUTPUT_MIB, max_uncompressed_gib=8,
    rights_register=None, rights_purpose="research",
):
    source, output = Path(source), Path(output)
    lower = source.name.lower()
    if not (lower.endswith(".csv.zst") or lower.endswith(".zip")):
        raise AISInputError("Input must be a NOAA daily .csv.zst or .zip archive")
    if output.suffix.lower() != ".csv" or source.resolve() == output.resolve():
        raise AISInputError("Output must be a different .csv file")
    if not (1 <= max_rows <= MAX_MATCHING_ROWS):
        raise AISInputError("max_rows must be in the supported range")
    if not (1 <= max_output_mib <= MAX_OUTPUT_MIB):
        raise AISInputError("max_output_mib must be in the supported range")
    if not (1 <= max_uncompressed_gib <= MAX_UNCOMPRESSED_GIB):
        raise AISInputError("max_uncompressed_gib must be in the supported range")
    a, b = utc(start), utc(end)
    if not (a < b and a.date() == b.date()):
        raise AISInputError("Use a positive time window within one UTC day")
    vintage = vintage_for(a.date())
    if vintage.compression != ("zip" if lower.endswith(".zip") else "zst"):
        raise AISInputError(f"{a.year} archives are {vintage.compression}-compressed ({vintage.layout})")
    if len(bbox) != 4 or not all(math.isfinite(float(v)) for v in bbox):
        raise AISInputError("Expected four finite bounding box values")
    w, s, e, n = map(float, bbox)
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise AISInputError("Invalid west/south/east/north bounding box")
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_COMPRESSED_BYTES:
        raise AISInputError("Source file is missing, empty, or exceeds compressed size cap")

    metadata = output.with_name(output.name + ".source.json")
    if output.exists() or metadata.exists():
        raise FileExistsError("Refusing overwrite of an existing extraction or metadata file")

    counters = {"rows_scanned": 0, "missing_value": 0, "invalid": 0, "outside_time": 0,
                "outside_bbox": 0, "selected": 0}
    detected = {"header_style": None}
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    temp_meta = metadata.with_name(metadata.name + ".partial")
    bytes_written = 0
    limit = max_output_mib * 1048576
    try:
        with _archive_text(source, max_uncompressed_gib) as text, temporary.open("xb") as target:
            reader = csv.DictReader(text)
            if not reader.fieldnames:
                raise AISInputError("Source archive has no CSV header")
            header = list(reader.fieldnames)
            detected["header_style"] = header_style(header)
            fields = {key: header_alias(header, key) for key in ("mmsi", "timestamp", "lat", "lon", "sog")}
            head = _csv_row_bytes(header)
            target.write(head)
            bytes_written += len(head)
            for row in reader:
                counters["rows_scanned"] += 1
                if None in row:
                    counters["invalid"] += 1
                    continue
                if any(not (row.get(fields[k]) or "").strip() for k in ("timestamp", "lat", "lon")):
                    counters["missing_value"] += 1
                    continue
                try:
                    when = parse_time(row[fields["timestamp"]])
                    lat = float(row[fields["lat"]])
                    lon = float(row[fields["lon"]])
                    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError("Invalid coordinate")
                except (ValueError, TypeError, KeyError, OverflowError):
                    counters["invalid"] += 1
                    continue
                if not a <= when <= b:
                    counters["outside_time"] += 1
                    continue
                if not (w <= lon <= e and s <= lat <= n):
                    counters["outside_bbox"] += 1
                    continue
                if counters["selected"] >= max_rows:
                    raise AISInputError("Matched rows exceed cap: refuse incomplete extraction")
                blob = _csv_row_bytes([row.get(key, "") for key in header])
                if bytes_written + len(blob) > limit:
                    raise AISInputError("Extracted CSV exceeds output byte cap")
                target.write(blob)
                bytes_written += len(blob)
                counters["selected"] += 1
        if counters["selected"] == 0:
            raise AISInputError("No observations matched; do not infer absence of vessel traffic")

        input_digest = sha256(source)
        rights = rights_receipt("noaa_ocm_ais_daily",
            dataset_version=f"{a.year}/archive-sha256:{input_digest}",
            purpose=rights_purpose, register_path=rights_register)
        report = {
            "source_type": "local_noaa_daily_archive",
            "input_filename": source.name,
            "input_sha256": input_digest,
            "output_filename": output.name,
            "output_sha256": sha256(temporary),
            "window_start_utc": a.isoformat().replace("+00:00", "Z"),
            "window_end_utc": b.isoformat().replace("+00:00", "Z"),
            "bbox_lon_lat": [w, s, e, n],
            "counts": counters,
            "bytes_written": bytes_written,
            "source_vintage": {"layout": vintage.layout, "year": a.year,
                               "expected_header_style": vintage.header_style,
                               "detected_header_style": detected["header_style"],
                               "missing_values": vintage.missing_values,
                               "layout_verification": vintage.verification},
            "limits": {"max_rows": max_rows, "max_output_mib": max_output_mib,
                       "max_uncompressed_gib": max_uncompressed_gib},
            "rights_status": rights["rights_status"],
            "rights_review": rights,
            "warning": "Origin of local archive and commercial reuse rights not independently authenticated.",
        }
        with temp_meta.open("x", encoding="utf-8") as meta:
            json.dump(report, meta, indent=2)
        os.replace(temporary, output)
        os.replace(temp_meta, metadata)
        return report
    except Exception:
        temporary.unlink(missing_ok=True)
        temp_meta.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise


def main():
    p = argparse.ArgumentParser(description="Extract Houston observations from a local daily NOAA AIS archive")
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--start", required=True,
                   help="YYYY-MM-DDTHH:MM:SSZ or ±HH:MM; 0-6 fraction digits; no surrounding space")
    p.add_argument("--end", required=True, help="Same grammar as --start")
    p.add_argument("--bbox", type=float, nargs=4, default=BBOX_HOUSTON)
    p.add_argument("--max-rows", type=int, default=MAX_MATCHING_ROWS)
    p.add_argument("--max-output-mib", type=int, default=DEFAULT_OUTPUT_MIB)
    p.add_argument("--max-uncompressed-gib", type=int, default=8)
    p.add_argument("--rights-register", type=Path, default=None)
    p.add_argument("--rights-purpose", choices=PURPOSES, default="research")
    a = p.parse_args()
    print(json.dumps(extract_archive(
        a.input, a.out, a.start, a.end, a.bbox,
        a.max_rows, a.max_output_mib, a.max_uncompressed_gib,
        rights_register=a.rights_register, rights_purpose=a.rights_purpose
    ), indent=2))


if __name__ == "__main__":
    main()
