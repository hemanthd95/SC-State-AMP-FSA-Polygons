#!/usr/bin/env python3
"""Christine Berry Zeigler: triangulate the printed Arista/Baxley road
intersection against authoritative Census TIGER centerlines, then register
the source photographed FSA aerial map to NAIP near that road crossing.
Does NOT invent producer property from the source mailing address.
"""
import json,math,requests,cv2,numpy as np,fitz,traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from shapely.geometry import shape,LineString
from shapely.ops import transform,nearest_points,unary_union
from pyproj import Transformer
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/batch2/christine_arista_baxley_registration"
OUT.mkdir(parents=True,exist_ok=True)
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP/Christine Berry Zeigler_FSA Map.pdf"
ROADS=["Arista","Baxley","Richardson"]
AGENT={"User-Agent":"SC-State-AMP research GIS/2026"}
WM=Transformer.from_crs(4326,3857,always_xy=True)
LL=Transformer.from_crs(3857,4326,always_xy=True)
def get(name):
 urls=[
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/2/query",
  "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/1/query",
 ]
 found=[]
 for url in urls:
  try:
   p=dict(where=f"NAME LIKE '%{name}%'",outFields="*",returnGeometry="true",outSR="4326",
     f="geojson",resultRecordCount=200,
     geometry="-81.5,32.8,-80.2,33.8",inSR=4326,geometryType="esriGeometryEnvelope",
     spatialRel="esriSpatialRelIntersects")
   r=requests.get(url,params=p,headers=AGENT,timeout=24)
   r.raise_for_status();d=r.json()
   if "features" not in d:continue
   for f in d["features"]:
    props=f.get("properties",{})
    actual=props.get("NAME","")
    if name.lower() not in actual.lower():continue
    geom=shape(f["geometry"])
    if geom.geom_type in ("LineString","MultiLineString"):
     cen=geom.representative_point()
     if -81.5<cen.x<-80.2 and 32.8<cen.y<33.8:
      found.append((actual,geom))
   if found:break
  except Exception as e:print("ROAD_QUERY_FAIL",name,str(e)[:180],flush=True)
 return found
road_info={}
for road in ROADS:
 arr=get(road)
 road_info[road]=[dict(actual=name,coordinates_count=len(g.coords) if g.geom_type=="LineString" else len(g.geoms),centroid=[g.centroid.x,g.centroid.y]) for name,g in arr]
 print("ROAD_GEOMETRY",road,road_info[road][:5],flush=True)
roads={name:get(name) for name in ROADS}
# arista/baxley intersection candidate, closest line geometry points.
a=[transform(WM.transform,geom) for name,geom in roads["Arista"]]
b=[transform(WM.transform,geom) for name,geom in roads["Baxley"]]
pairs=[]
for g in a:
 for h in b:
  dist=g.distance(h)
  u,v=nearest_points(g,h)
  mx,my=(u.x+v.x)/2,(u.y+v.y)/2
  lon,lat=LL.transform(mx,my)
  pairs.append(dict(distance_m=float(dist),lon=float(lon),lat=float(lat),mx=mx,my=my))
pairs.sort(key=lambda x:x["distance_m"])
assert pairs,"Arista/Baxley road geometry unavailable"
print("ROADS_CLOSEST",pairs[:7],flush=True)
anchors=[p for p in pairs[:4] if p["distance_m"]<200]
if not anchors:
 # not same junction according to Census: use midpoint of closest, but mark weak.
 anchors=pairs[:2]
summary=dict(farmer="Christine Berry Zeigler",source_pdf=SRC.name,
  target="1271/469/1",printed_fsa_acres=10.51,
  roads_found=road_info,closest_Arista_Baxley_distance_m=pairs[0]["distance_m"],
  road_junction_candidates=[{k:v for k,v in p.items() if k!="mx" and k!="my"} for p in pairs[:8]],
  status="NO_INDEPENDENT_AERIAL_REGISTRATION")
# Search around road geometries; ~8km from mailing address is acceptable if aerial matches.
views=core.source_views(SRC,1)
assert views,"Cannot extract scanned FSA image features"
S=950;EXTENT=1800.;STEP=725.
OFFSETS=[(x,y) for x in range(-3,4) for y in range(-3,4)]
OFFSETS.sort(key=lambda d:d[0]**2+d[1]**2)
tasks=[(a,provider,dx,dy) for a in anchors[:2] for provider in ("USGS_NAIP","ESRI_World") for dx,dy in OFFSETS[:25]]
def fetch(item):
 anchor,provider,dx,dy=item
 x=anchor["mx"]+dx*STEP;y=anchor["my"]+dy*STEP
 bb=[x-EXTENT/2,y-EXTENT/2,x+EXTENT/2,y+EXTENT/2]
 params=dict(bbox=",".join(f"{v:.2f}" for v in bb),bboxSR=3857,imageSR=3857,
         size=f"{S},{S}",format="jpg",f="image")
 try:
  r=requests.get(core.SERVICES[provider],params=params,headers=AGENT,timeout=30)
  r.raise_for_status()
  im=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if im is not None and im.shape[:2]==(S,S):return im,bb
 except:pass
 return None
best=None;loaded=0
with ThreadPoolExecutor(max_workers=10) as pool:
 future={pool.submit(fetch,task):task for task in tasks}
 for ft in as_completed(future):
  try:result=ft.result()
  except:result=None
  if not result:continue
  loaded+=1;im,bb=result
  for view in views:
   m=core.register(view,im)
   if m is None:continue
   rank=(bool(m["valid"]),float(m["score"]))
   if best is None or rank>best["rank"]:
    best=dict(m=m,v=view,im=im,bb=bb,task=future[ft],rank=rank)
summary["tiles_loaded"]=loaded;summary["tiles_requested"]=len(tasks)
if best:
 m=best["m"];v=best["v"]
 good=m["valid"] and m["inliers"]>=35 and m["rmse"]<2
 H=m["H"]@v["T"];H/=H[2,2]
 summary.update(status="ROAD_CONSTRAINED_NAIP_REGISTRATION_MATCH_FIELD_TRACE_NEEDED" if good else "WEAK_AERIAL_MATCH_NOT_ACCEPTED",
  image_matches=m["inliers"],rmse_px=round(m["rmse"],4),
  source_spread=m["spread_src"],target_spread=m["spread_dst"],
  provider=best["task"][1],offset=list(best["task"][2:]),
  tile_bbox_epsg3857=best["bb"],tile_size_px=S,
  source_pdf_pts_to_tile_homography=H.tolist())
 if good:
  crop=v["crop"]
  warped=cv2.warpPerspective(crop,m["H"],(S,S))
  mask=cv2.warpPerspective(np.full(crop.shape[:2],255,np.uint8),m["H"],(S,S))
  overlay=cv2.addWeighted(best["im"],.55,warped,.45,0);overlay[mask==0]=best["im"][mask==0]
  cv2.imwrite(str(OUT/"christine_naip_registration_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,87])
  cv2.imwrite(str(OUT/"christine_naip_reference_aerial.jpg"),best["im"],[cv2.IMWRITE_JPEG_QUALITY,85])
(OUT/"Christine_road_constrained_registration_QA.json").write_text(json.dumps(summary,indent=2)+"\n")
print("CHRISTINE_FINAL",summary["status"],"inliers",summary.get("image_matches"),"rmse",summary.get("rmse_px"),flush=True)
