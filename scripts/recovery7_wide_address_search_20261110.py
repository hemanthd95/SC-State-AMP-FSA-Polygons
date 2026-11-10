#!/usr/bin/env python3
"""Additional wider but bounded image registration centered on verified addresses.
A positive SIFT result remains only a candidate until field trace/acreage QA.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import json,math,traceback
import cv2,numpy as np
import recovery7_aerial_registration_20261110 as core

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery7_20261110"
TARG={x["name"]:x for x in core.TARGS}
TARGETS=["Albert Vareen","Tyrease Riley","Christopher Riley"]
R=core.R
SERVICE=core.SERVICES
SIZE=950
SPAN=2700.
STEP=1950.
BASE=core.ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
# Limit to a moderately sized local area; not an unbounded statewide search.
def fetch(t,provider,dx,dy):
 lon=t["unique_search_anchors"][0]["lon"];lat=t["unique_search_anchors"][0]["lat"]
 x,y=core.xy(lon,lat);x+=dx*STEP;y+=dy*STEP
 bbox=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
 params=dict(bbox=",".join(f"{v:.2f}" for v in bbox),bboxSR=3857,imageSR=3857,size=f"{SIZE},{SIZE}",format="jpg",f="image")
 try:
  import requests
  r=requests.get(SERVICE[provider],params=params,timeout=25);r.raise_for_status()
  a=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if a is not None and a.shape[:2]==(SIZE,SIZE):return a,bbox
 except:pass
 return None
def run(t):
 name=t["name"];folder=OUT/name.replace(" ","_")
 folder.mkdir(exist_ok=True)
 pages=t["pages"]
 if name=="Christopher Riley":pages=[2,3,4]
 views=[]
 for page in pages:
  views.extend(core.source_views(BASE/t["source_pdf"],page))
 results={}
 offsets=[(x,y) for x in range(-3,4) for y in range(-3,4)]
 offsets.sort(key=lambda d:d[0]**2+d[1]**2)
 # Stage 1: 49 Esri tiles out to ~7 km. Stage 2: NAIP only if no
 # real valid match for any target page. This avoids repeated NAIP calls.
 providers=["ESRI_World","USGS_NAIP"]
 total=0
 for provider in providers:
  jobs=[(provider,dx,dy) for dx,dy in offsets]
  with ThreadPoolExecutor(max_workers=10) as pool:
   pending={pool.submit(fetch,t,*j):j for j in jobs}
   for fut in as_completed(pending):
    prov,dx,dy=pending[fut]
    try:got=fut.result()
    except Exception:got=None
    if got is None:continue
    total+=1;tile,bb=got
    for view in views:
     match=core.register(view,tile)
     if match is None:continue
     # Exclude singular/tiny-area homographies; avoid false correspondence.
     if match["inliers"]<24 or match["rmse"]>2.2:continue
     pg=view["page_number"]
     score=(bool(match["valid"]),match["score"])
     prev=results.get(pg)
     if prev and score<=(bool(prev["match"]["valid"]),prev["match"]["score"]):continue
     results[pg]=dict(match=match,provider=prov,bbox=bb,dx=dx,dy=dy,
                      view=view,tile=tile)
  if any(q["match"]["valid"] and q["match"]["inliers"]>=65 for q in results.values()):
   print("ENOUGH",name,"provider",provider,flush=True)
   break
 summary=[]
 for pg in pages:
  record=dict(farmer=name,source_pdf=t["source_pdf"],page=pg,verified_address=t["address"],tiles_loaded=total)
  if pg in results:
   q=results[pg];m=q["match"];v=q["view"]
   H=m["H"]@v["T"];H/=H[2,2]
   record.update(status="WIDE_SOURCE_REGISTRATION_CANDIDATE_REQUIRES_SOURCE_FIELD_QA" if m["valid"] else "WEAK_ALIGNMENT",
     inliers=m["inliers"],rmse_px=m["rmse"],source_spread_px=m["spread_src"],target_spread_px=m["spread_dst"],
     valid=m["valid"],provider=q["provider"],bbox_epsg3857=q["bbox"],
     tile_size=SIZE,page_pdf_to_tile_H=H.tolist(),view=v["name"],grid_offset=[q["dx"],q["dy"]])
   if m["valid"]:
    warped=cv2.warpPerspective(v["crop"],m["H"],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.ones(v["crop"].shape[:2],np.uint8)*255,m["H"],(SIZE,SIZE))
    overlay=cv2.addWeighted(q["tile"],.55,warped,.45,0)
    overlay[mask==0]=q["tile"][mask==0]
    cv2.imwrite(str(folder/f"wide_page{pg}_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,82])
    cv2.imwrite(str(folder/f"wide_page{pg}_tile.jpg"),q["tile"],[cv2.IMWRITE_JPEG_QUALITY,82])
  else:record["status"]="NO_WIDE_ALIGNMENT"
  summary.append(record)
  print("WIDE_RESULT",name,pg,record["status"],record.get("inliers"),flush=True)
 (folder/"wide_registration_report.json").write_text(json.dumps(summary,indent=2))
 return summary
def main():
 all=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  futs={pool.submit(run,TARG[name]):name for name in TARGETS}
  for f in as_completed(futs):
   try:result=f.result()
   except Exception as exc:
    name=futs[f];result=[dict(name=name,error=str(exc),traceback=traceback.format_exc()[-900:])]
    print("WIDE_ERROR",name,str(exc)[:220],flush=True)
   all.extend(result)
   (OUT/"wide_registration_summary.json").write_text(json.dumps(all,indent=2))
 print("WIDE_DONE",len(all),flush=True)
if __name__=="__main__":main()
