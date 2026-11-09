"""Bounded USACE Navigation Facilities point-catalog acquisition (SPEC-004).

The official ArcGIS FeatureServer stores point geometry, not berth/anchorage
polygons. No positional match constitutes independent vessel-event evidence.
Remote acquisition is opt-in; all unit tests use mocked HTTP responses.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LAYER = "https://services7.arcgis.com/n1YM8pTrFmm7L4hs/ArcGIS/rest/services/Docks/FeatureServer/0"
CATALOG = "https://catalog.data.gov/dataset/docks"
HOUSTON = (-95.70, 29.10, -94.20, 30.10)
FIELDS = (
    "OBJECTID", "NAV_UNIT_ID", "NAV_UNIT_NAME", "FAC_TYPE",
    "PORT_NAME", "WTWY_NAME", "DATA_RECORD_STATUS"
)
MAX_PAGES = 20
MAX_FEATURES = 2000
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class FacilityDataError(ValueError):
    """Official facility response is unavailable, truncated or invalid."""


def _bbox(bbox):
    if len(bbox) != 4:
        raise FacilityDataError("Bounding box must contain west,south,east,north")
    try:
        values = tuple(float(x) for x in bbox)
    except (ValueError, TypeError) as exc:
        raise FacilityDataError("Bounding box contains invalid coordinate") from exc
    w, s, e, n = values
    if not all(map(math.isfinite, values)) or not (
        -180 <= w < e <= 180 and -90 <= s < n <= 90
    ):
        raise FacilityDataError("Invalid bounded longitude/latitude rectangle")
    return values


def query_url(bbox=HOUSTON, offset=0, page_size=250):
    """Construct a query against an immutable, explicitly selected service URL."""
    w, s, e, n = _bbox(bbox)
    if not (1 <= page_size <= 500 and 0 <= offset < MAX_FEATURES):
        raise FacilityDataError("Query paging exceeds configured limits")
    params = {
        "where": "1=1", "outFields": ",".join(FIELDS), "f": "json",
        "returnGeometry": "true", "geometryType": "esriGeometryEnvelope",
        "geometry": json.dumps({"xmin": w, "ymin": s, "xmax": e, "ymax": n,
                                "spatialReference": {"wkid": 4326}}, separators=(",", ":")),
        "inSR": 4326, "outSR": 4326, "spatialRel": "esriSpatialRelIntersects",
        "orderByFields": "OBJECTID ASC",
        "resultOffset": offset, "resultRecordCount": page_size,
    }
    return LAYER + "/query?" + urlencode(params)


def _read_json(response):
    declared = getattr(response, "headers", {}).get("Content-Length")
    if declared is not None and int(declared) > MAX_RESPONSE_BYTES:
        raise FacilityDataError("USACE response exceeds byte cap")
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise FacilityDataError("USACE response exceeds byte cap")
    try:
        parsed = json.loads(data)
    except (UnicodeError, ValueError) as exc:
        raise FacilityDataError("USACE service returned non-JSON content") from exc
    if not isinstance(parsed, dict) or "error" in parsed:
        raise FacilityDataError("USACE service returned an error response")
    if not isinstance(parsed.get("features"), list):
        raise FacilityDataError("USACE response has no feature array")
    return parsed


def collect(bbox=HOUSTON, page_size=250, max_features=MAX_FEATURES, opener=None):
    bounds = _bbox(bbox)
    if not (1 <= max_features <= MAX_FEATURES):
        raise FacilityDataError("max_features out of allowed range")
    records, seen = [], set()
    source_requests = []
    offset = 0
    for page in range(MAX_PAGES):
        url = query_url(bounds, offset, page_size)
        source_requests.append(url)
        request = Request(url, headers={"User-Agent": "HarborLens-research/0.1", "Accept": "application/json"})
        with (opener or urlopen)(request, timeout=45) as response:
            payload = _read_json(response)
        features = payload["features"]
        if not features:
            break
        for item in features:
            if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
                raise FacilityDataError("Malformed facility attributes")
            attributes = item["attributes"]
            location = item.get("geometry")
            if not isinstance(location, dict):
                raise FacilityDataError("USACE facility geometry is missing")
            if "x" not in location or "y" not in location:
                raise FacilityDataError("USACE service must supply POINT coordinates, not polygons")
            try:
                lon, lat = float(location["x"]), float(location["y"])
                oid = int(attributes["OBJECTID"])
            except (KeyError, ValueError, TypeError) as exc:
                raise FacilityDataError("Facility ID or coordinate is invalid") from exc
            if not (math.isfinite(lon) and math.isfinite(lat)
                    and -180 <= lon <= 180 and -90 <= lat <= 90):
                raise FacilityDataError("Invalid facility coordinates")
            if not (bounds[0] <= lon <= bounds[2] and bounds[1] <= lat <= bounds[3]):
                continue  # Independent check in case ArcGIS returned extra features.
            if oid in seen:
                raise FacilityDataError("Repeated OBJECTID across pagination; unsafe source consistency")
            if len(records) >= max_features:
                raise FacilityDataError("Facility count exceeds configured cap; no truncated output")
            seen.add(oid)
            values = {key.lower(): attributes.get(key) for key in FIELDS}
            values.update({"facility_status": "reference_point_only",
                           "event_verification": "not_verified"})
            records.append({
                "type": "Feature", "id": str(oid),
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": values
            })
        if len(records) >= max_features and (
            payload.get("exceededTransferLimit") or len(features) >= page_size
        ):
            raise FacilityDataError("Facility count reached cap without proof of complete result")
        offset += len(features)
        if offset >= MAX_FEATURES:
            if payload.get("exceededTransferLimit") or len(features) >= page_size:
                raise FacilityDataError("Pagination reached source cap without terminal page")
            break
        if not payload.get("exceededTransferLimit") and len(features) < page_size:
            break
    else:
        raise FacilityDataError("Exceeded allowed USACE pagination attempts")
    if not records:
        raise FacilityDataError("No facility points in selected area; not evidence of missing infrastructure")
    records.sort(key=lambda item: int(item["id"]))
    geojson = {"type": "FeatureCollection", "features": records}
    return geojson, source_requests


def save_catalog(output, bbox=HOUSTON, page_size=250, max_features=MAX_FEATURES, opener=None):
    output = Path(output)
    if output.suffix.lower() != ".geojson":
        raise FacilityDataError("Output filename must use .geojson")
    if output.exists():
        raise FileExistsError("Refusing to overwrite an existing facility catalog")
    sidecar = output.with_name(output.name + ".source.json")
    if sidecar.exists():
        raise FileExistsError("Refusing to overwrite existing source metadata")
    geometry, urls = collect(bbox=bbox, page_size=page_size, max_features=max_features, opener=opener)
    raw = (json.dumps(geometry, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    metadata = {
        "source_agency": "USACE / USDOT BTS NTAD (ArcGIS hosted feature layer)",
        "service_url": LAYER,
        "catalog_url": CATALOG,
        "queries": urls,
        "geometric_type": "Point",
        "output_epsg": 4326,
        "license_status": "review_required",
        "source_date_status": "current service snapshot, not dated historical geometry",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feature_count": len(geometry["features"]),
        "output_sha256": hashlib.sha256(raw).hexdigest(),
        "warning": "Facility points are NOT berth/anchorage polygons or verified vessel states.",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".partial")
    tmpmeta = sidecar.with_name(sidecar.name + ".partial")
    try:
        with tmp.open("xb") as f:
            f.write(raw)
        with tmpmeta.open("x", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        os.replace(tmp, output)
        os.replace(tmpmeta, sidecar)
    except Exception:
        tmp.unlink(missing_ok=True)
        tmpmeta.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise
    return metadata


def main():
    parser = argparse.ArgumentParser(description="Fetch bounded USACE Navigation Facilities points — not berth polygons")
    parser.add_argument("--bbox", nargs=4, type=float, default=HOUSTON, metavar=("W", "S", "E", "N"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--page-size", type=int, default=250)
    parser.add_argument("--max-features", type=int, default=MAX_FEATURES)
    a = parser.parse_args()
    print(json.dumps(save_catalog(a.out, bbox=a.bbox, page_size=a.page_size, max_features=a.max_features), indent=2))


if __name__ == "__main__":
    main()
