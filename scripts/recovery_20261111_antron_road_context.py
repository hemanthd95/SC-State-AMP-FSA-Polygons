#!/usr/bin/env python3
"""Locate physical Cinnabar Rd and Gordon Dr FSA map neighborhoods with
official road centerlines, then collect NAIP/Esri aerial context for map registration.
Never derive a field polygon merely from a road or residential address.
"""
import io,json,math,re,traceback,requests
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import shape,Point,mapping
from shapely.ops import transform,nearest_points
from pyproj import Transformer,Geod
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery_20261111/Antron_Williams"
OUT.mkdir(parents=True,exist_ok=True)
SESSION=requests.Session();SESSION.headers.update({"User-Agent":"SCState-AMP-FSA-FieldVerification/2026 (research GIS)"})
G=Geod(ellps="WGS84")
WM=Transformer.from_crs(4326,3857,always_xy=True)
LL=Transformer.from_crs(3857,4326,always_xy=True)
ROADS=["Cinnabar Rd","Gordon Dr"]
TARGETS=[("Cinnabar Rd",33.37,-80.7),("Gordon Dr",33.37,-80.7)]
def fetch_json(url,params,timeout=40):
 r=SESSION.get(url,params=params,timeout=timeout);r.raise_for_status()
 obj=r.json()
 if "error" in obj:raise ValueError(str(obj["error"])[:200])
 return obj
def roads_from_tiger():
 sources=[
 "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/2/query",
 "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/1/query",
 "https://services2.arcgis.com/bUKn95BqgpYYTnx3/ArcGIS/rest/services/Main_Public_Tax_Parcel_Map_WFL1/FeatureServer/5/query"]
 found=[]
 for url in sources:
  for n in ROADS:
   for where in [f"NAME = '{n}'",f"NAME LIKE '%{n.split()[0]}%'"]:
    try:
     d=fetch_json(url,dict(where=where,outFields="*",returnGeometry="true",outSR="4326",f="geojson",resultRecordCount=1000,geometry="-81.4,33.0,-80.3,33.9",geometryType="esriGeometryEnvelope",inSR=4326,spatialRel="esriSpatialRelIntersects"),45)
     for f in d.get("features",[]):
      props=f.get("properties",{})
      name=props.get("NAME") or props.get("ROAD_NAME") or props.get("FULLNAME") or props.get("STREETNAME") or props.get("StreetName") or ""
      if n.split()[0].lower() not in str(name).lower():continue
      try:
       geo=shape(f["geometry"])
       if geo.geom_type not in ("LineString","MultiLineString") or geo.is_empty:continue
       center=geo.representative_point()
       if not (-81.4<center.x<-80.3 and 33.0<center.y<33.9):continue
      except:continue
      found.append({"type":"Feature","properties":dict(name=n,source_url=url,raw_name=str(name)),
                    "geometry":f["geometry"]})
     if found:print("ROAD_SEARCH",url,n,where,"found",len(found),flush=True)
    except Exception as exc:print("ROAD_SEARCH_FAIL",url,n,str(exc)[:120],flush=True)
 return found
def fallback_geocode(road):
 url="https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates"
 for loc in [f"{road}, Orangeburg County, South Carolina",f"{road}, Rowesville, South Carolina"]:
  try:
   d=fetch_json(url,dict(SingleLine=loc,f="json",maxLocations=4),24)
   for item in d.get("candidates",[]):
    p=item["location"];score=float(item.get("score",0))
    if 33.1<p["y"]<33.8 and -81.5<p["x"]<-80.2:
     return {"lat":p["y"],"lon":p["x"],"score":score,"address":item["address"],"source":"arcgis_street_geocoder"}
  except Exception as e:print("GEOCODE_FAIL",str(e)[:80],flush=True)
 return None
def get_map(cx,cy,extent,provider="ESRI_World"):
 bbox=(cx-extent/2,cy-extent/2,cx+extent/2,cy+extent/2)
 url=("https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
      if provider=="USGS_NAIP" else
      "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export")
 q=dict(bbox=",".join(f"{v:.2f}" for v in bbox),bboxSR=3857,imageSR=3857,
   size="1500,1500",format="jpg",f="image")
 r=SESSION.get(url,params=q,timeout=50);r.raise_for_status()
 im=Image.open(io.BytesIO(r.content)).convert("RGB")
 if im.size!=(1500,1500):raise ValueError("Unexpected raster shape")
 return im,bbox
def main():
 roads=roads_from_tiger()
 (OUT/"named_street_centerlines.geojson").write_text(json.dumps({"type":"FeatureCollection","features":roads},indent=2))
 summary={"farm_id":"11990","tract_id":"44081","producer":"Antron Williams",
   "fsa_page_reference":{"5":{"road":"Cinnabar Rd","fields":["7","18","19","20"]},
                          "7":{"road":"Gordon Dr","fields":["61","3","16"]}},
   "not_used_for_location":["county name printed on source FSA PDFs","producer W-9 mailing address"],
   "roads":{},"map_downloads":[]}
 centers={}
 for n in ROADS:
  ff=[f for f in roads if f["properties"]["name"]==n]
  if ff:
   group=transform(WM.transform,shape(ff[0]["geometry"]))
   for feat in ff[1:]:
    pass
   center=group.representative_point()
   centers[n]=(center.x,center.y)
   lon,lat=LL.transform(center.x,center.y)
   summary["roads"][n]=dict(road_center=[lon,lat],provider="US_Census_TIGERweb",count_segments=len(ff),
      source_wgs84_geometry=ff[0]["geometry"])
  else:
   gf=fallback_geocode(n)
   if gf:
    centers[n]=WM.transform(gf["lon"],gf["lat"]);summary["roads"][n]=gf
 if len(centers)==2:
  d=math.hypot(centers[ROADS[0]][0]-centers[ROADS[1]][0],centers[ROADS[0]][1]-centers[ROADS[1]][1])
  summary["road_reference_centers_distance_m"]=round(d,1)
  print("ROADS_CENTER_DISTANCE_M",round(d,1),flush=True)
 for n,center in centers.items():
  for extent in [1400,2700]:
   for provider in ["USGS_NAIP","ESRI_World"]:
    try:
     im,bbox=get_map(*center,extent,provider)
     d=ImageDraw.Draw(im)
     for ft in roads:
      geo=shape(ft["geometry"])
      ff=geo.geoms if geo.geom_type=="MultiLineString" else [geo]
      for line in ff:
       pp=[WM.transform(x,y) for x,y in line.coords]
       xy=[((x-bbox[0])/(bbox[2]-bbox[0])*1500,
          (bbox[3]-y)/(bbox[3]-bbox[1])*1500) for x,y in pp]
       if len(xy)>1:
        d.line(xy,fill="#F2CA22" if ft["properties"]["name"]==n else "#21DFF2",width=5)
     d.text((28,20),f"{n} | {provider} | {extent} m extent | YELLOW/CYAN public road centerlines",
       fill="white",stroke_width=3,stroke_fill="black")
     fname=n.replace(" ","_")+f"_{provider}_{extent}m.jpg"
     im.save(OUT/fname,quality=86,optimize=True)
     summary["map_downloads"].append(dict(file=fname,bbox_epsg3857=bbox,size=[1500,1500],
        imagery=provider,road=n))
     print("MAP",fname,flush=True)
    except Exception as e:print("MAP_FAILED",n,provider,extent,str(e)[:170],flush=True)
 (OUT/"road_search_summary.json").write_text(json.dumps(summary,indent=2)+"\n")
 print("SUMMARY",json.dumps({"roads":summary["roads"],"distance_m":summary.get("road_reference_centers_distance_m"),
   "map_download_count":len(summary["map_downloads"])})[:5000],flush=True)
if __name__=="__main__":main()
