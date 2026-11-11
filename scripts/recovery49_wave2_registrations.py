#!/usr/bin/env python3
"""Address-first wave 2 (ten source PDFs), real USGS NAIP/Esri image matching.
Only source-photo registration candidates are generated. Actual field polygon
needs source Farm/Tract/Field identification, outline tracing and acreage QA.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,requests,cv2,numpy as np,math,traceback
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/wave2"
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT.mkdir(parents=True,exist_ok=True)
TARGETS=[
 ("Samuel Lance Jr","Samuel Lance JR.pdf","3740/10333/2161","134 Oxford Lane, Allendale, SC 29810"),
 ("Tiffany Loadholt","Tifanny Loadholt_FSA_Map.pdf","3779/10394/54","115 Oxford Lane, Allendale, SC 29810"),
 ("LaTonya Flood","Latonya Flood_FSAmap.pdf","13739/45688/2","327 Underwood Ln, Summerville, SC 29486"),
 ("Ivan Flood","Iven Flood_FSA_Map.pdf","577/1397/1","337 Underwood Ln, Summerville, SC 29486"),
 ("Jan Davis Boneparte","Jan Davis-Boneparte_FSA_Map.pdf","3549/8353/2","114 Generation Lane, Cameron, SC 29030"),
 ("Sharon Taylor","Sharon Taylor_Farm_FSA_Map.pdf","1134/1563/8","7881 White Point Road, Ravenel, SC 29470"),
 ("Christian Richburg","Christian Richburg_FSA Map.pdf","1375/1022/1","3574 Rev JW Carter Road, Summerton, SC 29148"),
 ("Eartha Pinckney","Eartha_Pinckney_FSA_Map.pdf","6579/22687/11","865 McDanieltown Rd, Ridgeville, SC 29472"),
 ("Deone Jones","Deone Jones_FSA Map.pdf","1659/7406/18","122 Hitching Post Road, Greenwood, SC 29646"),
 ("David Gates","David Gates FSA_Map.pdf","3107/16607/34","220 Island Creek Road, Cowpens, SC 29330")
]
R=6378137.;SIZE=900;SPAN=1750.;STEP=760.
OFFSETS=[(0,0),(1,0),(0,1),(-1,0),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1),
         (2,0),(-2,0),(0,2),(0,-2)]
AGENT={"User-Agent":"SCStateAMP-FieldValidation/1.0 (noncommercial research)"}
def geocode(address):
 out=[]
 try:
  d=requests.get("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
       params=dict(address=address,benchmark="Public_AR_Current",vintage="Current_Current",format="json"),
       headers=AGENT,timeout=22).json()
  for rec in d.get("result",{}).get("addressMatches",[])[:2]:
   p=rec["coordinates"]
   out.append(dict(provider="US_CENSUS_ADDRESS",lon=float(p["x"]),lat=float(p["y"]),
                   matched_address=rec.get("matchedAddress")))
 except Exception as e:print("GEOCODE_CENSUS_FAIL",address,str(e)[:90],flush=True)
 if not out:
  try:
   d=requests.get("https://nominatim.openstreetmap.org/search",
      params=dict(q=address,format="jsonv2",limit=2),headers=AGENT,timeout=20).json()
   for rec in d[:2]:
    out.append(dict(provider="OSM_NOMINATIM",lon=float(rec["lon"]),lat=float(rec["lat"]),
         matched_address=rec.get("display_name")))
  except Exception as e:print("GEOCODE_OSM_FAIL",address,str(e)[:90],flush=True)
 return [q for q in out if -83<q["lon"]<-78 and 31.5<q["lat"]<35.8]
def tile(anchor,p,dx,dy):
 xx,yy=core.xy(anchor["lon"],anchor["lat"]);xx+=STEP*dx;yy+=STEP*dy
 bbox=[xx-SPAN/2,yy-SPAN/2,xx+SPAN/2,yy+SPAN/2]
 params=dict(bbox=",".join(f"{z:.2f}" for z in bbox),bboxSR=3857,imageSR=3857,
             size=f"{SIZE},{SIZE}",format="jpg",f="image")
 try:
  resp=requests.get(core.SERVICES[p],params=params,headers=AGENT,timeout=28)
  resp.raise_for_status()
  im=cv2.imdecode(np.frombuffer(resp.content,np.uint8),cv2.IMREAD_COLOR)
  if im is not None and im.shape[:2]==(SIZE,SIZE):return im,bbox
 except Exception:pass
 return None
def run(t):
 name,source,target,address=t
 folder=OUT/"".join(c if c.isalnum() else "_" for c in name)
 folder.mkdir(parents=True,exist_ok=True)
 result=dict(name=name,source_pdf=source,source_page=1,
             enrolled_farm_tract_field=target,excel_farm_address=address)
 anchors=geocode(address)
 if name in ("Tiffany Loadholt","Ivan Flood") and not anchors:
  # Nearby street, still an address SEARCH HINT, not a field location.
  alt="134 Oxford Lane, Allendale, SC 29810" if name=="Tiffany Loadholt" else "327 Underwood Ln, Summerville, SC 29486"
  anchors=geocode(alt)
  result["fallback_road_address"]=alt
 result["geocoded_address_anchors"]=anchors
 if not anchors:
  result["status"]="ADDRESS_NOT_GEOCODED"
  (folder/"registration_qa.json").write_text(json.dumps(result,indent=2)+"\n")
  print("W2_RESULT",name,result["status"],flush=True)
  return result
 views=core.source_views(SRC/source,1)
 if not views:
  result["status"]="FSA_SOURCE_NO_USABLE_IMAGE_FEATURES"
  (folder/"registration_qa.json").write_text(json.dumps(result,indent=2)+"\n")
  return result
 tasks=[(a,p,dx,dy) for a in anchors[:1] for p in ["USGS_NAIP","ESRI_World"]
        for dx,dy in OFFSETS]
 best=None;loaded=0
 def get(job):
  a,p,dx,dy=job
  return job,tile(a,p,dx,dy)
 with ThreadPoolExecutor(max_workers=7) as pool:
  futures=[pool.submit(get,job) for job in tasks]
  for ft in as_completed(futures):
   try:job,fetch=ft.result()
   except Exception:continue
   if fetch is None:continue
   loaded+=1;im,bbox=fetch
   for view in views:
    m=core.register(view,im)
    if m is None:continue
    score=(m["valid"],m["score"])
    if best is None or score>best["score"]:
     best=dict(m=m,view=view,im=im,bbox=bbox,task=job,score=score)
 result["tile_requests"]=len(tasks)
 result["loaded_tiles"]=loaded
 if best is None:
  result["status"]="NO_MATCH_IN_LOCAL_ADDRESS_WINDOW"
 else:
  m=best["m"];view=best["view"];A=m["H"]@view["T"];A/=A[2,2]
  a,p,dx,dy=best["task"]
  result.update(
   status="REGISTERED_PHOTO_CANDIDATE_NEEDS_FIELD_TRACE" if m["valid"] else "WEAK_IMAGE_MATCH_REJECTED",
   inliers=m["inliers"],rmse_px=round(m["rmse"],3),
   source_spread=m["spread_src"],image_spread=m["spread_dst"],
   valid_geometric_match=bool(m["valid"]),
   address_anchor=a,imagery_provider=p,tile_offset=[dx,dy],
   tile_bbox_epsg3857=best["bbox"],tile_size_px=SIZE,
   source_pdf_page_points_to_tile_H=A.tolist())
  if m["valid"]:
   src=view["crop"]
   warped=cv2.warpPerspective(src,m["H"],(SIZE,SIZE))
   mask=cv2.warpPerspective(np.full(src.shape[:2],255,np.uint8),m["H"],(SIZE,SIZE))
   overlay=cv2.addWeighted(best["im"],.55,warped,.45,0)
   overlay[mask==0]=best["im"][mask==0]
   cv2.imwrite(str(folder/"validated_registration_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,82])
   cv2.imwrite(str(folder/"aerial_tile.jpg"),best["im"],[cv2.IMWRITE_JPEG_QUALITY,80])
 (folder/"registration_qa.json").write_text(json.dumps(result,indent=2)+"\n")
 print("W2_RESULT",name,result["status"],result.get("inliers"),result.get("rmse_px"),flush=True)
 return result
def main():
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  futures={pool.submit(run,x):x for x in TARGETS}
  for ft in as_completed(futures):
   try:r=ft.result()
   except Exception as e:
    r=dict(name=futures[ft][0],status="ERROR",error=str(e),
       traceback=traceback.format_exc()[-1000:])
   results.append(r)
   (OUT/"wave2_batch_summary.json").write_text(json.dumps(results,indent=2)+"\n")
 print("W2_SUMMARY",len(results),"GEOGRAPHIC_MATCHES",
       sum(x.get("valid_geometric_match",False) for x in results),flush=True)
if __name__=="__main__":main()
