#!/usr/bin/env python3
"""Batch1 outstanding extra tract source images:
Charles Bright Jr. Farm2715/Tract3021 PDF p2
Jasper Summers Farm13709/Tract45512 PDF p3
Register against independently georeferenced USGS NAIP, preferring prior
same-farm accepted geodetic match as controlled search origin.
Emit no new field polygons unless image correspondences pass.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,traceback,requests,cv2,numpy as np,math
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/batch1_extra_tracts"
OUT.mkdir(parents=True,exist_ok=True)
SOURCES=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
TARGETS=[
 dict(name="Charles Bright Jr.",q="analysis/recovery49_20261111/wave4/Charles_Bright_Jr_/registration_qa.json",
    pdf="Bright, Charles, JR_ FSAmap.pdf",page=2,tract="3021",farm="2715",
    field_ids=["4","6","7"]),
 dict(name="Jasper Summers",q="analysis/recovery49_20261111/wave4/Jasper_Summers/registration_qa.json",
    pdf="Jasper Summers FSA Map.pdf",page=3,tract="45512",farm="13709",
    field_ids=["16","27"])
]
SIDE=900;SPAN=1750.;STEP=800.
SERVICES=core.SERVICES
OFFSETS=[(dx,dy) for dx in range(-3,4) for dy in range(-3,4)]
OFFSETS.sort(key=lambda p:p[0]*p[0]+p[1]*p[1])
def candidate_tile(q,dx,dy,provider):
 bb=q["tile_bbox_epsg3857"]
 cx=(bb[0]+bb[2])/2+dx*STEP
 cy=(bb[1]+bb[3])/2+dy*STEP
 bbox=[cx-SPAN/2,cy-SPAN/2,cx+SPAN/2,cy+SPAN/2]
 params=dict(bbox=",".join(f"{x:.2f}" for x in bbox),bboxSR=3857,
      imageSR=3857,size=f"{SIDE},{SIDE}",format="jpg",f="image")
 try:
  response=requests.get(SERVICES[provider],params=params,timeout=30)
  response.raise_for_status()
  im=cv2.imdecode(np.frombuffer(response.content,np.uint8),cv2.IMREAD_COLOR)
  if im is not None and im.shape[:2]==(SIDE,SIDE):return im,bbox
 except Exception:pass
 return None
def run(t):
 q=json.loads((ROOT/t["q"]).read_text())
 views=core.source_views(SOURCES/t["pdf"],t["page"])
 assert len(views)>=1
 folder=OUT/t["name"].replace(" ","_")
 folder.mkdir(parents=True,exist_ok=True)
 tasks=[(dx,dy,provider) for dx,dy in OFFSETS for provider in ("USGS_NAIP","ESRI_World")]
 best=None;loaded=0
 def fetch(job):
  dx,dy,provider=job
  return job,candidate_tile(q,dx,dy,provider)
 with ThreadPoolExecutor(max_workers=9) as pool:
  future={pool.submit(fetch,job):job for job in tasks}
  for ft in as_completed(future):
   try:job,image=ft.result()
   except Exception:continue
   if image is None:continue
   loaded+=1;im,bbox=image
   for view in views:
    m=core.register(view,im)
    if m is None:continue
    rank=(m["valid"],m["score"])
    if best is None or rank>best["rank"]:
     best=dict(m=m,view=view,im=im,bbox=bbox,job=job,rank=rank)
 result=dict(farmer=t["name"],source_pdf=t["pdf"],source_page=t["page"],
      farm_id=t["farm"],tract_id=t["tract"],fields_to_reconcile=t["field_ids"],
      source_control=t["q"],tiles_requested=len(tasks),tiles_loaded=loaded)
 if best is None:
  result["status"]="NO_IMAGE_MATCH_WITHIN_SAME_FARM_LOCALITY"
 else:
  m=best["m"];v=best["view"];H=m["H"]@v["T"];H/=H[2,2]
  result.update(status="REGISTERED_CANDIDATE_REQUIRES_SOURCE_TRACE_AND_AREA_QA" if m["valid"] and m["inliers"]>=45 else "WEAK_NOT_ACCEPTED",
      inliers=m["inliers"],rmse_px=m["rmse"],
      inlier_spread_src=m["spread_src"],inlier_spread_target=m["spread_dst"],
      valid_nondegenerate=bool(m["valid"]),source_view=v["name"],
      source_pdf_points_to_tile_H=H.tolist(),
      tile_bbox_epsg3857=best["bbox"],tile_size_px=SIDE,
      provider=best["job"][2],offset_tiles=list(best["job"][:2]))
  im=best["im"]
  crop=v["crop"];warped=cv2.warpPerspective(crop,m["H"],(SIDE,SIDE))
  mask=cv2.warpPerspective(np.full(crop.shape[:2],255,np.uint8),m["H"],(SIDE,SIDE))
  overlay=cv2.addWeighted(im,.55,warped,.45,0)
  overlay[mask==0]=im[mask==0]
  cv2.imwrite(str(folder/"candidate_aerial_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,84])
  cv2.imwrite(str(folder/"candidate_reference_aerial.jpg"),im,[cv2.IMWRITE_JPEG_QUALITY,84])
 (folder/"extra_tract_qa.json").write_text(json.dumps(result,indent=2)+"\n")
 print("EXTRA_TRACT",t["name"],result["status"],"inliers",result.get("inliers"),"rmse",result.get("rmse_px"),flush=True)
 return result
with ThreadPoolExecutor(max_workers=2) as pool:
 futs=[pool.submit(run,t) for t in TARGETS]
 results=[]
 for f in as_completed(futs):
  try:result=f.result()
  except Exception as exc:result=dict(status="ERROR",error=str(exc),traceback=traceback.format_exc()[-1600:])
  results.append(result)
  (OUT/"extra_tracts_summary.json").write_text(json.dumps(results,indent=2)+"\n")
print("DONE",len(results),flush=True)
