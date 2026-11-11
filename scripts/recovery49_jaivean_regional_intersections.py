#!/usr/bin/env python3
"""Search rural road T-junctions around the source farm-road corridor, not
the false Excel coordinates. Aerial screenshots are for visual source matching
only. The FSA 3988 screenshot features roads with bearings ~35 and ~95 deg
(mod 180) meeting at the southwestern point of a large cropland triangle.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,math,requests,io
from shapely.geometry import shape,Point,LineString,MultiLineString
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/Jaivean_Spann/Regional_Road_Junction_Search"
OUT.mkdir(parents=True,exist_ok=True)
SESSION=requests.Session();SESSION.headers.update({"User-Agent":"SC-State-AMP-NRCS/road-intersection-research"})
url="https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/2/query"
bbox="-80.42,33.52,-80.16,33.76"
params=dict(where="1=1",outFields="NAME,MTFCC",returnGeometry="true",
 outSR="4326",f="geojson",resultRecordCount=3000,
 geometry=bbox,geometryType="esriGeometryEnvelope",inSR=4326,
 spatialRel="esriSpatialRelIntersects")
r=SESSION.get(url,params=params,timeout=60);r.raise_for_status();data=r.json()
if "error" in data:raise RuntimeError(data["error"])
print("ROAD_FEATURES",len(data.get("features",[])),flush=True)
toM=Transformer.from_crs(4326,32617,always_xy=True)
toW=Transformer.from_crs(32617,4326,always_xy=True)
geoms=[];name=[]
for feature in data.get("features",[]):
 try:
  g=transform(toM.transform,shape(feature["geometry"]))
  parts=list(g.geoms) if g.geom_type=="MultiLineString" else [g]
  for one in parts:
   if one.length<30:continue
   geoms.append(one);name.append(str(feature.get("properties",{}).get("NAME") or "Unnamed road"))
 except:continue
tree=STRtree(geoms)
def bear(g,p):
 t=g.project(p)
 a=g.interpolate(max(0,t-38))
 b=g.interpolate(min(g.length,t+38))
 dx=b.x-a.x;dy=b.y-a.y
 return math.degrees(math.atan2(dx,dy))%180
def diff(a,b):return min(abs(a-b),180-abs(a-b))
candidate=[]
for i,g in enumerate(geoms):
 if i%200==0:print("PROCESS_ROAD",i,len(geoms),flush=True)
 for j in tree.query(g):
  j=int(j)
  if j<=i:continue
  h=geoms[j]
  if name[i]==name[j] and name[i]!="Unnamed road":continue
  intersection=g.intersection(h)
  if intersection.is_empty:continue
  points=[]
  if isinstance(intersection,Point):points=[intersection]
  elif intersection.geom_type=="MultiPoint":points=list(intersection.geoms)
  else:continue
  for p in points:
   a=bear(g,p);b=bear(h,p)
   fit=min(diff(a,35)+diff(b,95),diff(a,95)+diff(b,35))
   if fit>33:continue
   lon,lat=toW.transform(p.x,p.y)
   if not (-80.42<lon<-80.16 and 33.52<lat<33.76):continue
   # We only rank within 11km of mapped named Rev JW Carter Rd, not a nationwide search.
   center=(-80.29,33.64)
   d=math.hypot((lon-center[0])*92500,(lat-center[1])*111000)
   if d>13500:continue
   score=fit+.0009*d
   candidate.append(dict(lon=lon,lat=lat,first_road=name[i],second_road=name[j],
    bearing1=round(a,1),bearing2=round(b,1),score=round(score,2),
    road_fit_deg=round(fit,2),distance_km_from_known_road=round(d/1000,1)))
candidate.sort(key=lambda x:x["score"])
unique=[]
for p in candidate:
 if all(math.hypot((p["lon"]-q["lon"])*92500,(p["lat"]-q["lat"])*111000)>250 for q in unique):
  unique.append(p)
 if len(unique)>=25:break
print("ROAD_JUNCTION_CANDIDATES",len(candidate),"DISTINCT",len(unique),flush=True)
def img(job):
 idx,record=job;R=6378137
 x=R*math.radians(record["lon"])
 y=R*math.log(math.tan(math.pi/4+math.radians(record["lat"])/2))
 extent=740
 bb=[x-extent/2,y-extent/2,x+extent/2,y+extent/2]
 params=dict(bbox=",".join(f"{z:.3f}" for z in bb),bboxSR=3857,imageSR=3857,
  size="850,850",format="jpg",f="image")
 try:
  r=requests.get("https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage",
   params=params,timeout=42)
  r.raise_for_status()
  image=Image.open(io.BytesIO(r.content)).convert("RGB")
  if image.size!=(850,850):return None
  d=ImageDraw.Draw(image)
  d.ellipse((421,421,429,429),fill="magenta")
  font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",20)
  d.rectangle((0,0,850,65),fill="black")
  d.text((14,10),f"#{idx+1} {record['first_road'][:23]} / {record['second_road'][:23]}",
         font=font,fill="white")
  d.text((14,36),f"bearings {record['bearing1']:.0f},{record['bearing2']:.0f}  fit {record['road_fit_deg']:.0f}°",
         font=font,fill="yellow")
  filename=f"Candidate_{idx+1:02d}.jpg"
  image.save(OUT/filename,quality=81,optimize=True)
  return filename
 except Exception as e:
  print("IMAGE_ERROR",idx,str(e)[:90],flush=True);return None
take=unique[:16]
with ThreadPoolExecutor(max_workers=8) as pool:
 out=list(pool.map(img,enumerate(take)))
for p,filename in zip(take,out):p["aerial_preview"]=filename
thumb=Image.new("RGB",(4*390,4*400),"white")
for i,rec in enumerate(take):
 if not rec.get("aerial_preview"):continue
 t=Image.open(OUT/rec["aerial_preview"]);t.thumbnail((390,390))
 thumb.paste(t,((i%4)*390,(i//4)*400))
thumb.save(OUT/"Intersection_Contact_Sheet.jpg",quality=87,optimize=True)
(OUT/"candidates.json").write_text(json.dumps({
  "status":"CANDIDATES_ONLY_NO_FARM_GEOREFERENCED",
  "source_photo":["Farm3988 Tract4673 Field1, image screenshot"],
  "source_road_bearings_approx":[35,95],
  "spatial_window_wgs84":bbox,
  "features_checked":len(geoms),"junctions_matched_before_filter":len(candidate),
  "candidates":unique,
  "warning":"Road bearings and proximity to farm address not sufficient for acceptance; require matching NAIP cropped-field texture/shape and acreage."},indent=2)+"\n")
print("FINISHED",len(take),"IMAGES",sum(bool(x) for x in out),flush=True)
