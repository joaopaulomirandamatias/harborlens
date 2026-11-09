"""Opt-in NOAA designated anchorage polygons (SPEC-004).

Queries a fixed NOAA ArcGIS MapServer layer. Output polygons are current
reference geometry, NOT historical 2024 truth or navigation-grade data.
No network request occurs at import or during existing AIS workflows.
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

LAYER = "https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0"
CATALOG = "https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0"
HOUSTON = (-95.70, 29.10, -94.20, 30.10)
MAX_FEATURES = 500
MAX_BYTES = 8 * 1024 * 1024
BATCH_SIZE = 50


class PolygonSourceError(ValueError):
    """Source polygon data are unavailable, excessive, or malformed."""


def _bbox(bounds):
    if len(bounds) != 4:
        raise PolygonSourceError("Bounding box must contain west,south,east,north")
    try:
        w, s, e, n = [float(x) for x in bounds]
    except (ValueError, TypeError) as exc:
        raise PolygonSourceError("Invalid bounding box value") from exc
    if not (all(math.isfinite(x) for x in (w,s,e,n))
            and -180 <= w < e <= 180 and -90 <= s < n <= 90):
        raise PolygonSourceError("Invalid bounding box extent")
    return w, s, e, n


def _query_url(params):
    return LAYER + "/query?" + urlencode(params)


def list_ids_url(bbox=HOUSTON):
    w,s,e,n=_bbox(bbox)
    return _query_url({
        "where":"1=1","geometry":json.dumps({"xmin":w,"ymin":s,"xmax":e,"ymax":n,
                "spatialReference":{"wkid":4326}},separators=(",",":")),
        "geometryType":"esriGeometryEnvelope","inSR":4326,
        "spatialRel":"esriSpatialRelIntersects","returnIdsOnly":"true","f":"json",
    })


def batch_url(ids):
    if not ids or len(ids)>BATCH_SIZE or any(not isinstance(x,int) or x<0 for x in ids):
        raise PolygonSourceError("Invalid object ID batch")
    return _query_url({
        "objectIds":",".join(str(x) for x in ids),"outFields":"*",
        "returnGeometry":"true","outSR":4326,"f":"geojson",
    })


def _read_json(opener, url):
    req=Request(url,headers={"User-Agent":"HarborLens-research/0.1","Accept":"application/json"})
    with opener(req,timeout=45) as response:
        declared=getattr(response,"headers",{}).get("Content-Length")
        if declared is not None and int(declared)>MAX_BYTES:
            raise PolygonSourceError("NOAA source response exceeds byte cap")
        raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:
            raise PolygonSourceError("NOAA source response exceeds byte cap")
    try:
        data=json.loads(raw)
    except (UnicodeError,ValueError) as exc:
        raise PolygonSourceError("NOAA service returned non-JSON data") from exc
    if not isinstance(data,dict) or "error" in data:
        raise PolygonSourceError("NOAA source returned an error response")
    return data


def _count_vertices(value):
    if isinstance(value,(list,tuple)):
        if len(value)>=2 and all(isinstance(x,(int,float)) for x in value[:2]):
            return 1
        return sum(_count_vertices(x) for x in value)
    return 0


def collect(bbox=HOUSTON, max_features=MAX_FEATURES, opener=None):
    """Select official current polygons by bounded source IDs, not by page offsets."""
    bounds=_bbox(bbox)
    if not 1<=max_features<=MAX_FEATURES:
        raise PolygonSourceError("max_features out of allowed range")
    client=opener or urlopen
    requests=[list_ids_url(bounds)]
    ids_doc=_read_json(client,requests[0])
    ids=ids_doc.get("objectIds")
    if not isinstance(ids,list):
        raise PolygonSourceError("NOAA response lacks objectIds list")
    if not ids:
        raise PolygonSourceError("No polygons returned; not evidence of no anchorage")
    if any(not isinstance(x,int) or x<0 for x in ids) or len(set(ids))!=len(ids):
        raise PolygonSourceError("Unexpected or duplicate source object IDs")
    ids=sorted(ids)
    if len(ids)>max_features:
        raise PolygonSourceError("Source polygon count exceeds limit; refuse truncation")
    id_field=ids_doc.get("objectIdFieldName")
    if not isinstance(id_field,str) or not id_field:
        raise PolygonSourceError("Source objectIdFieldName was not supplied")
    features={}
    for i in range(0,len(ids),BATCH_SIZE):
        group=ids[i:i+BATCH_SIZE]
        url=batch_url(group)
        requests.append(url)
        doc=_read_json(client,url)
        if doc.get("type")!="FeatureCollection" or not isinstance(doc.get("features"),list):
            raise PolygonSourceError("NOAA response is not a GeoJSON FeatureCollection")
        for item in doc["features"]:
            if not isinstance(item,dict) or item.get("type")!="Feature":
                raise PolygonSourceError("Malformed polygon feature")
            geom=item.get("geometry") or {}
            if geom.get("type") not in ("Polygon","MultiPolygon"):
                raise PolygonSourceError("NOAA layer returned non-polygon geometry")
            if not isinstance(geom.get("coordinates"),list) or _count_vertices(geom["coordinates"])>100000:
                raise PolygonSourceError("Polygon geometry is missing or exceeds vertex limit")
            p=item.get("properties") or {}
            source_id=item.get("id",p.get(id_field))
            try:
                source_id=int(source_id)
            except (TypeError,ValueError) as exc:
                raise PolygonSourceError("Polygon lacks a valid source object ID") from exc
            if source_id not in group or source_id in features:
                raise PolygonSourceError("NOAA returned unexpected/duplicate feature ID")
            # Shapely provides robust ring topology and validity checks.
            try:
                from shapely.geometry import shape
                polygon=shape(geom)
            except ImportError as exc:
                raise PolygonSourceError("Install optional geo extra: pip install 'harborlens[geo]'") from exc
            except Exception as exc:
                raise PolygonSourceError("NOAA geometry cannot be parsed") from exc
            if polygon.is_empty or not polygon.is_valid or polygon.area<=0:
                raise PolygonSourceError("NOAA polygon is empty, invalid or degenerate")
            if not all(math.isfinite(x) for x in polygon.bounds):
                raise PolygonSourceError("NOAA polygon coordinates are not finite")
            features[source_id]={
                "type":"Feature","id":str(source_id),"geometry":geom,
                "properties":{
                    "source_object_id":source_id,
                    "source_layer":"NOAA Designated Anchorage Areas",
                    "source_name":str(p.get("name") or p.get("NAME") or ""),
                    "geometry_review_status":"unreviewed",
                    "historical_validity":"not_verified",
                    "event_verification":"not_verified",
                }
            }
    if set(features)!=set(ids):
        raise PolygonSourceError("Incomplete NOAA polygon response")
    return {"type":"FeatureCollection","features":[features[i] for i in ids]},requests


def save_polygons(out,bbox=HOUSTON,max_features=MAX_FEATURES,opener=None):
    out=Path(out)
    if out.suffix.lower()!=".geojson":
        raise PolygonSourceError("Output must end in .geojson")
    sidecar=out.with_name(out.name+".source.json")
    if out.exists() or sidecar.exists():
        raise FileExistsError("Refusing to overwrite existing polygon or sidecar")
    data,urls=collect(bbox,max_features,opener)
    encoded=(json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
    side={
        "source_agency":"NOAA",
        "service_url":LAYER,
        "query_urls":urls,
        "geometry_type":"Polygon/MultiPolygon",
        "bbox_lon_lat":list(_bbox(bbox)),
        "epsg":4326,
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "feature_count":len(data["features"]),
        "output_sha256":hashlib.sha256(encoded).hexdigest(),
        "rights_status":"review_required",
        "historical_validity":"not_verified",
        "geometry_review_status":"unreviewed",
        "warning":"Current anchorage polygons are reference only, NOT confirmed historical berth/waiting events or navigation boundaries.",
    }
    out.parent.mkdir(parents=True,exist_ok=True)
    tmp=out.with_name(out.name+".partial")
    tmpmeta=sidecar.with_name(sidecar.name+".partial")
    try:
        with tmp.open("xb") as f:
            f.write(encoded)
        with tmpmeta.open("x",encoding="utf-8") as f:
            json.dump(side,f,indent=2)
        os.replace(tmp,out)
        os.replace(tmpmeta,sidecar)
    except Exception:
        tmp.unlink(missing_ok=True)
        tmpmeta.unlink(missing_ok=True)
        out.unlink(missing_ok=True)
        raise
    return side


def main():
    p=argparse.ArgumentParser(description="Fetch NOAA current anchorage polygons for research; NOT FOR NAVIGATION")
    p.add_argument("--bbox",nargs=4,type=float,default=HOUSTON,metavar=("W","S","E","N"))
    p.add_argument("--out",required=True,type=Path)
    p.add_argument("--max-features",type=int,default=MAX_FEATURES)
    a=p.parse_args()
    print(json.dumps(save_polygons(a.out,a.bbox,a.max_features),indent=2))

if __name__=="__main__":
    main()
