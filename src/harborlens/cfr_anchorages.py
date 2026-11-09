"""Source-pinned 2024 CFR §110.197 anchorage coordinate transcription audit.

A regulatory description is not automatically WGS84 navigational geometry.
In particular 33 CFR §110.1(d) requires appropriate corrections where the
regulation does not explicitly identify NAD83. Source coordinate topology
must not be repaired silently and no regulatory area is promoted to verified
port behavior. No network, AIS processing or source editing is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

SOURCE_URL = "https://www.govinfo.gov/content/pkg/CFR-2024-title33-vol1/html/CFR-2024-title33-vol1.htm"
AMENDMENT_URL = "https://www.govinfo.gov/content/pkg/FR-2018-04-27/pdf/2018-08873.pdf"
REFERENCE_DATE = date(2024, 7, 1)
VERSION = "cfr-2024-title33-vol1-sec110-197-v1"
DMS_RE = re.compile(r"^(\d{1,3})°(\d{1,2})'(\d{1,2}(?:\.\d+)?)\"([NSEW])$")


class RegulatoryGeometryError(ValueError):
    """Unsafe or incompatible historical regulation coordinates."""


# Exact coordinate tokens from the 2024 annual CFR section 110.197(a),
# latitude first, longitude second. DMS punctuation normalized only.
# DO NOT silently reorder points or infer a missing horizontal datum.
BOUNDARIES = {
    "A": (
        ("29°20'48.5\"N", "94°42'54.0\"W"),
        ("29°20'43.0\"N", "94°44'46.5\"W"),
        ("29°21'15.0\"N", "94°44'27.0\"W"),
        ("29°21'05.0\"N", "94°42'52.0\"W"),
    ),
    "B": (
        ("29°20'43.0\"N", "94°44'46.5\"W"),
        ("29°20'37.0\"N", "94°46'08.0\"W"),
        ("29°21'14.0\"N", "94°45'50.0\"W"),
        ("29°21'15.0\"N", "94°44'27.0\"W"),
    ),
    "C": (
        ("29°20'39.0\"N", "94°46'07.5\"W"),
        ("29°21'06.1\"N", "94°47'00.2\"W"),
        ("29°21'24.0\"N", "94°46'34.0\"W"),
        ("29°21'14.5\"N", "94°45'49.0\"W"),
    ),
    "A_EAST": (
        ("29°21'5.87\"N", "094°42'52.7\"W"),
        ("29°20'53.99\"N", "094°42'7.13\"W"),
        ("29°20'45.31\"N", "094°42'37.75\"W"),
        ("29°20'39.16\"N", "094°42'7.81\"W"),
    ),
}


def parse_dms(token: str, kind: str) -> float:
    """Strict DMS transcription only: not a CRS transformation."""
    match = DMS_RE.fullmatch(token)
    if match is None:
        raise RegulatoryGeometryError("Invalid DMS coordinate transcription")
    degrees, minutes, seconds, hemisphere = match.groups()
    if hemisphere not in ("NS" if kind == "lat" else "EW"):
        raise RegulatoryGeometryError("Wrong hemisphere for coordinate axis")
    try:
        seconds_dec = Decimal(seconds)
        numeric = Decimal(degrees) + Decimal(minutes) / 60 + seconds_dec / 3600
    except InvalidOperation as exc:
        raise RegulatoryGeometryError("Invalid coordinate seconds") from exc
    if not (0 <= int(minutes) < 60 and 0 <= seconds_dec < 60 and
            numeric <= (90 if kind == "lat" else 180)):
        raise RegulatoryGeometryError("Out-of-range DMS coordinate")
    return round(float(numeric) * (-1 if hemisphere in "SW" else 1), 10)


def _study_date(value: str):
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError("bad date format")
        return date.fromisoformat(value)
    except ValueError as exc:
        raise RegulatoryGeometryError("Use an exact YYYY-MM-DD study date") from exc


def inspect_regulated_areas(study_date: str = "2024-07-01"):
    """Return audited DMS polygons; deliberately NEVER GeoJSON/verified zones."""
    try:
        from shapely.geometry import Polygon
        from shapely.validation import explain_validity
    except ImportError as exc:
        raise RegulatoryGeometryError("Install the optional geo dependency") from exc
    requested = _study_date(study_date)
    date_status = ("prior_to_available_annual_edition_unverified"
                   if requested < REFERENCE_DATE
                   else "documented_at_2024_annual_edition_only")
    records = []
    for name, raw_vertices in BOUNDARIES.items():
        coords = [[parse_dms(lon, "lon"), parse_dms(lat, "lat")]
                  for lat, lon in raw_vertices]
        # Use the literal published sequence; a convex hull/sort would silently
        # create invented boundaries, especially for Anchorage A East.
        ring = coords + [coords[0]]
        poly = Polygon(ring)
        source_datum = ("NAD83_explicit" if name == "A_EAST" else
                        "not_explicitly_specified")
        topology_status = "valid_literal_ring" if poly.is_valid and poly.area > 0 else "invalid_literal_ring"
        blockers = []
        if requested < REFERENCE_DATE:
            blockers.append("historical_date_not_established_by_2024_07_01_edition")
        if source_datum != "NAD83_explicit":
            blockers.append("horizontal_datum_requires_independent_resolution")
        if topology_status != "valid_literal_ring":
            blockers.append("published_vertex_sequence_requires_expert_review")
        blockers.append("no_independent_operational_event_truth")
        records.append({
            "id": name,
            "display_name": "Anchorage A East" if name == "A_EAST" else "Anchorage " + name,
            "source_reference": "33 CFR 110.197(a)",
            "source_datum": source_datum,
            "source_lat_lon_dms": [{"latitude":lat, "longitude":lon} for lat, lon in raw_vertices],
            "transcribed_lon_lat_in_source_datum": coords,
            "ring_closed": ring[0] == ring[-1],
            "literal_ring_topology": topology_status,
            "topology_detail": "no_issue_detected_in_literal_order" if topology_status == "valid_literal_ring"
                               else explain_validity(poly),
            "historical_study_status": date_status,
            "review_blockers": blockers,
            "ais_spatial_join_permitted": False,
            "verified_anchorage_or_waiting": False,
        })
    return {
        "schema_version": "regulatory-anchorage-audit-v1",
        "source_authority": "US Government Publishing Office annual CFR",
        "source_url": SOURCE_URL,
        "regulation": "33 CFR 110.197",
        "regulation_general_datum_caveat": "33 CFR 110.1(d)",
        "source_edition_date": REFERENCE_DATE.isoformat(),
        "reference_version": VERSION,
        "evidence_date_scope": date_status,
        "study_date": requested.isoformat(),
        "regulatory_text_digest": hashlib.sha256(
            json.dumps(BOUNDARIES,sort_keys=True,separators=(",",":")).encode("utf-8")
        ).hexdigest(),
        "areas": records,
        "source_regulatory_date_validity": "as_of_2024_07_01_only",
        "source_document_authenticity": "official_public_web_reference_not_locally_hash_verified",
        "rights_status": "review_required_for_downstream_datasets",
        "warning": "NOT WGS84 GeoJSON. Literal regulatory coordinates are not approved for AIS joins, navigation, berth occupancy or anchorage/waiting claims.",
    }


def save_audit(output: Path, study_date: str = "2024-07-01"):
    output = Path(output)
    if output.suffix.lower() != ".json" or output.exists():
        raise RegulatoryGeometryError("Use a new .json output; refusing overwrite")
    result = inspect_regulated_areas(study_date)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".partial")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            json.dump(result,handle,indent=2)
        temporary.replace(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return result


def main():
    parser = argparse.ArgumentParser(description="Audit 2024 CFR anchorage coordinates; NO AIS matching or navigation")
    parser.add_argument("--study-date",default="2024-07-01")
    parser.add_argument("--out",required=True,type=Path)
    args = parser.parse_args()
    result=save_audit(args.out,args.study_date)
    print(json.dumps({"study_date":result["study_date"],"area_count":len(result["areas"]),
                      "topology_blockers":[x["id"] for x in result["areas"] if x["literal_ring_topology"]!="valid_literal_ring"],
                      "ais_spatial_join_permitted":False},indent=2))


if __name__=="__main__":
    main()
