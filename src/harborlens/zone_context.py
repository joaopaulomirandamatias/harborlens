"""Historical candidate-centroid vs. local polygon spatial CONTEXT (SPEC-004).

Only a descriptive geometrical overlap is computed. No port-call, anchoring,
waiting, berth occupancy or historical validity inference is authorized.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

MAX_INPUT_MIB = 32
MAX_CANDIDATES = 50000
MAX_ZONES = 500


class ZoneContextError(ValueError):
    """Unusable or unsupported candidate/anchorage geometry."""


def _load(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size > MAX_INPUT_MIB * 1048576:
        raise ZoneContextError("Missing or oversized GeoJSON input")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ZoneContextError("Invalid GeoJSON document") from exc


def _digest(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def spatial_context(candidates, polygons, output):
    """Annotate unvalidated POINT candidate centroids with NOAA polygon overlap."""
    try:
        from shapely.geometry import shape, Point
    except ImportError as exc:
        raise ZoneContextError("Install the optional geo extra: pip install 'harborlens[geo]'") from exc
    candidates, polygons, output = Path(candidates), Path(polygons), Path(output)
    if output.suffix.lower()!=".geojson" or output.resolve() in (candidates.resolve(), polygons.resolve()):
        raise ZoneContextError("Output must be another .geojson file")
    sidecar=output.with_name(output.name+".source.json")
    if output.exists() or sidecar.exists():
        raise FileExistsError("Output/sidecar already exists")
    dataset=_load(candidates)
    zones=_load(polygons)
    if dataset.get("type")!="FeatureCollection" or zones.get("type")!="FeatureCollection":
        raise ZoneContextError("Both inputs must be GeoJSON FeatureCollections")
    case=dataset.get("features")
    zlist=zones.get("features")
    if not isinstance(case,list) or not isinstance(zlist,list) or len(case)>MAX_CANDIDATES or len(zlist)>MAX_ZONES:
        raise ZoneContextError("Input feature count exceeds supported limits")
    if not zlist:
        raise ZoneContextError("An empty polygon layer cannot prove absence of anchorages")
    prepared=[]
    for item in zlist:
        if item.get("type")!="Feature":
            raise ZoneContextError("Malformed polygon feature")
        raw=item.get("geometry") or {}
        if raw.get("type") not in ("Polygon","MultiPolygon"):
            raise ZoneContextError("Only Polygon/MultiPolygon accepted; facility points are not zones")
        try:
            geom=shape(raw)
        except Exception as exc:
            raise ZoneContextError("Polygon could not be parsed") from exc
        if geom.is_empty or not geom.is_valid or geom.area<=0:
            raise ZoneContextError("Invalid or degenerate polygon")
        source_id=item.get("id")
        if not isinstance(source_id,(int,str)) or not str(source_id):
            raise ZoneContextError("Polygon source id required")
        prepared.append((str(source_id),geom))
    if len({x[0] for x in prepared})!=len(prepared):
        raise ZoneContextError("Duplicate polygon identifiers")
    prepared.sort(key=lambda x:x[0])
    results=[]
    counts={"total_candidates":0,"one_overlap":0,"multiple_overlaps":0,"no_overlap":0}
    for item in case:
        if item.get("type")!="Feature" or (item.get("geometry") or {}).get("type")!="Point":
            raise ZoneContextError("Candidate input must contain only Point features")
        pt=item["geometry"].get("coordinates")
        if not isinstance(pt,list) or len(pt)<2:
            raise ZoneContextError("Candidate point coordinates missing")
        try:
            x,y=float(pt[0]),float(pt[1])
        except (ValueError,TypeError) as exc:
            raise ZoneContextError("Invalid candidate coordinate") from exc
        if not (math.isfinite(x) and math.isfinite(y) and -180<=x<=180 and -90<=y<=90):
            raise ZoneContextError("Out-of-range candidate coordinate")
        props=item.get("properties")
        if not isinstance(props,dict) or props.get("confidence_label")!="unvalidated":
            raise ZoneContextError("Only explicitly unvalidated stationary candidates are supported")
        matches=[ident for ident,geo in prepared if geo.covers(Point(x,y))]
        if len(matches)==1:
            status="possible_spatial_overlap"
            counts["one_overlap"]+=1
        elif matches:
            status="ambiguous_multiple_polygons"
            counts["multiple_overlaps"]+=1
        else:
            status="no_polygon_overlap_observed"
            counts["no_overlap"]+=1
        updated=dict(props)
        updated["zone_context"]={
            "status":status,
            "source_feature_ids":matches,
            "spatial_method":"centroid_within_or_on_polygon_boundary",
            "historical_validity":"not_verified",
            "interpretation":"unverified_spatial_context_only",
            "navigation_suitability":"NOT_FOR_NAVIGATION",
        }
        results.append({"type":"Feature","geometry":{"type":"Point","coordinates":[x,y]},
                        "properties":updated})
        counts["total_candidates"]+=1
    output.parent.mkdir(parents=True,exist_ok=True)
    result={"type":"FeatureCollection","features":results}
    raw=(json.dumps(result,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
    if len(raw)>MAX_INPUT_MIB*1048576:
        raise ZoneContextError("Annotated GeoJSON exceeds output size cap")
    metadata={
        "schema_version":"context-v0.1",
        "candidate_sha256":_digest(candidates),
        "polygon_sha256":_digest(polygons),
        "output_sha256":hashlib.sha256(raw).hexdigest(),
        "counts":counts,
        "rights_status":"review_required",
        "historical_validity":"not_verified",
        "warning":"Centroid overlay is not confirmed anchorage, berth, port call, waiting, or navigational data.",
    }
    tmp=output.with_name(output.name+".partial")
    meta_tmp=sidecar.with_name(sidecar.name+".partial")
    try:
        with tmp.open("xb") as f:
            f.write(raw)
        with meta_tmp.open("x",encoding="utf-8") as f:
            json.dump(metadata,f,indent=2)
        tmp.replace(output)
        meta_tmp.replace(sidecar)
    except Exception:
        tmp.unlink(missing_ok=True)
        meta_tmp.unlink(missing_ok=True)
        output.unlink(missing_ok=True)
        raise
    return metadata


def main():
    p=argparse.ArgumentParser(description="Unverified spatial context for stationary candidate centroids")
    p.add_argument("--candidates",required=True,type=Path)
    p.add_argument("--polygons",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    print(json.dumps(spatial_context(a.candidates,a.polygons,a.out),indent=2))

if __name__=="__main__":
    main()
