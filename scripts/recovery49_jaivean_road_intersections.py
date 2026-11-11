#!/usr/bin/env python3
"""GIS road geolocation for Jaivean Spann. Exact road and nearby intersections,
source map bearings approx NE35° and E95° based on FSA 3988 screenshot.
Not sufficient to register fields without aerial agreement.
"""
import json,math,requests,zipfile,io
from pathlib import Path
from shapely.geometry import shape,LineString,Point,mapping,box
from shapely.ops import transform,nearest_points
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/Jaivean_Spann/Road_Intersection_Candidates"
OUT.mkdir(parents=True,exist_ok=True)
def ask(url,q):
 r=requests.get(url,params=q,timeout=40);r.raise_for_status();d=r.json()
 if "error" in d:raise RuntimeError(d["error"])
 return d
layer="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/2/query"
roads=ask(layer,dict(where="NAME = 'Reverend J W Carter Rd'",outFields="*",
 returnGeometry="true",outSR="4326",f="geojson",resultRecordCount=1000,
 geometry="-80.7,33.4,-80.05,33.9",geometryType="esriGeometryEnvelope",
 inSR=4326,spatialRel="esriSpatialRelIntersects"))
ff=[x for x in roads.get("features",[]) if x["properties"].get("NAME")=="Reverend J W Carter Rd"]
print("EXACT_ROAD_SEGMENTS",len(ff),flush=True)
if not ff:raise RuntimeError("no official exact road")
forward=Transformer.from_crs(4326,32617,always_xy=True)
backward=Transformer.from_crs(32617,4326,always_xy=True)
segments=[transform(forward.transform,shape(f["geometry"])) for f in ff]
for q in segments:
 print("SEGMENT",round(q.length,1),len(q.coords),[list(backward.transform(*x)) for x in (q.coords[0],q.coords[-1])],flush=True)
largest=max(segments,key=lambda q:q.length)
minx,miny,maxx,maxy=largest.bounds
# Local TIGER roads: envelope around the entire Rev JW Carter segment + 700m.
x0,y0=backward.transform(minx-700,miny-700)
x1,y1=backward.transform(maxx+700,maxy+700)
d=ask(layer,dict(where="1=1",outFields="NAME,MTFCC",returnGeometry="true",outSR="4326",
 f="geojson",resultRecordCount=2500,
 geometry=f"{x0},{y0},{x1},{y1}",geometryType="esriGeometryEnvelope",
 inSR=4326,spatialRel="esriSpatialRelIntersects"))
others=[]
for f in d.get("features",[]):
 try:
  nm=str(f["properties"].get("NAME") or "")
  g=transform(forward.transform,shape(f["geometry"]))
  if g.is_empty or g.distance(largest)>90 or nm=="Reverend J W Carter Rd":continue
  others.append(dict(nm=nm,geom=g))
 except Exception:continue
print("NEARBY_ROADS",len(others),flush=True)
candidates=[]
for item in others:
 if not item["nm"]:continue
 road=item["geom"]
 near1,near2=nearest_points(largest,road)
 dist=near1.distance(near2)
 if dist>38:continue
 cx,cy=near1.x,near1.y
 chain_dist=largest.project(near1)
 def bear(g,point,r=40):
  at=g.project(point);a=g.interpolate(max(0,at-r));b=g.interpolate(min(g.length,at+r))
  e=b.x-a.x;n=b.y-a.y
  return (math.degrees(math.atan2(e,n))%180)
 major=bear(largest,near1)
 cross=bear(road,near2)
 angle=min(abs(major-cross),180-abs(major-cross))
 lon,lat=backward.transform(cx,cy)
 # From source1: FSA photo road pair 35 degrees vs 94 degrees from north.
 # No assumption either of the named roads is the 35deg branch.
 fit=min(abs(major-35)+abs(cross-95),abs(major-95)+abs(cross-35))
 if 33.25<lat<34.0 and -80.8<lon<-80.05:
  candidates.append(dict(lon=lon,lat=lat,name=item["nm"],distance_m=round(dist,1),
                        road_bearing_deg=round(major,1),other_bearing_deg=round(cross,1),
                        difference_deg=round(angle,1),fit_score=round(fit,1),
                        linear_position_m=round(chain_dist,1)))
candidates=sorted(candidates,key=lambda c:(c["fit_score"],c["distance_m"]))
p={"source":"US_Census_TIGERweb_Transportation_LargeScale","exact_name":"Reverend J W Carter Rd",
 "road_feature_collection":{"type":"FeatureCollection","features":ff},
 "all_segment_lengths_m":[round(g.length,1) for g in segments],
 "bboxes_wgs84":[[minx,miny,maxx,maxy]],
 "nearby_intersections":candidates[:40],
 "source_photo_road_bearings_approx_deg":[35,95],
 "note":"Street and intersection angles are search controls only, not validated farm vertices"}
(OUT/"exact_road_intersections.json").write_text(json.dumps(p,indent=2)+"\n")
for q in candidates[:30]:print("INTERSECTION",q,flush=True)
