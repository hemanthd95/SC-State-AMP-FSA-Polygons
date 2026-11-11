#!/usr/bin/env python3
"""Find Joe Hilliard's CORRECT Farm13859/Tract45814 photographed FSA page.
A second Joe PDF for Farm6528 is NOT the enrolled farm. This task searches
the correct photographed map with contrast-stabilized SIFT across a wider
address-centered NAIP region. Never substitute source Field35/36/37 for
enrolled Field20.
"""
from pathlib import Path
import math,json,requests,cv2,numpy as np
from concurrent.futures import ThreadPoolExecutor,as_completed
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/"analysis/recovery49_20261111/batch2/joe_enrolled_farm13859_registration"
out.mkdir(parents=True,exist_ok=True)
pdf=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP/Joe_Hillard_FSA_Map.pdf"
views=core.source_views(pdf,1)
assert views,"Photographed Joe 13859 image has no extractable imagery views"
anchor=(-80.50430450531,33.464418972005)
cx,cy=core.xy(*anchor)
SIZE=950;EXTENT=2400.;STEP=1650.
offs=[(dx,dy) for dx in range(-8,9) for dy in range(-8,9)]
offs.sort(key=lambda p:p[0]*p[0]+p[1]*p[1])
def get(job):
 dx,dy,provider=job
 x=cx+dx*STEP;y=cy+dy*STEP
 bb=[x-EXTENT/2,y-EXTENT/2,x+EXTENT/2,y+EXTENT/2]
 params=dict(bbox=",".join(f"{v:.2f}" for v in bb),
    bboxSR=3857,imageSR=3857,size=f"{SIZE},{SIZE}",format="jpg",f="image")
 try:
  r=requests.get(core.SERVICES[provider],params=params,timeout=30)
  r.raise_for_status()
  im=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if im is not None and im.shape[:2]==(SIZE,SIZE):return im,bb
 except Exception:return None
 return None
best=None;loaded=0
for provider in ["USGS_NAIP","ESRI_World"]:
 for k in range(0,len(offs),42):
  jobs=[(dx,dy,provider) for dx,dy in offs[k:k+42]]
  with ThreadPoolExecutor(max_workers=10) as pool:
   futures={pool.submit(get,job):job for job in jobs}
   for f in as_completed(futures):
    try:result=f.result()
    except Exception:result=None
    if result is None:continue
    loaded+=1;im,bb=result
    for view in views:
     m=core.register(view,im)
     if m is None:continue
     rank=(bool(m["valid"]),m["score"])
     if best is None or rank>best["rank"]:
      best=dict(m=m,view=view,img=im,bb=bb,job=futures[f],rank=rank)
      print("JOE_FARM13859_CANDIDATE",provider,loaded,m["inliers"],m["rmse"],m["valid"],futures[f][:2],flush=True)
  if best and best["m"]["valid"] and best["m"]["inliers"]>=80 and best["m"]["rmse"]<1.5:break
 if best and best["m"]["valid"] and best["m"]["inliers"]>=80 and best["m"]["rmse"]<1.5:break
qa=dict(producer="Joe Hilliard",source_pdf=pdf.name,
 source_farm="13859",source_tract="45814",source_fields=["35","36","37"],
 enrolled_target="13859/45814/20",
 anchor=anchor,tiles_loaded=loaded,search_radius_km=13.2,
 caveat="Field20 is not present on provided Farm13859 source map; cannot claim farmer complete by mapping Fields35/36/37.")
if best:
 m=best["m"];v=best["view"]
 H=m["H"]@v["T"];H/=H[2,2]
 strong=m["valid"] and m["inliers"]>=65 and m["rmse"]<1.8
 qa.update(status="SOURCE_FARM13859_GEOREGISTERED_FIELD20_ABSENT" if strong else "WEAK_IMAGE_MATCH_NOT_ACCEPTED",
 inliers=m["inliers"],rmse_px=m["rmse"],registered_source_farm=True,
 provider=best["job"][2],tile_offset=list(best["job"][:2]),bbox_epsg3857=best["bb"],
 tile_size_px=SIZE,source_pdf_pts_to_tile_H=H.tolist(),
 source_spread=m["spread_src"],target_spread=m["spread_dst"])
 if strong:
  crop=v["crop"];warped=cv2.warpPerspective(crop,m["H"],(SIZE,SIZE))
  mask=cv2.warpPerspective(np.full(crop.shape[:2],255,np.uint8),m["H"],(SIZE,SIZE))
  image=cv2.addWeighted(best["img"],.55,warped,.45,0);image[mask==0]=best["img"][mask==0]
  cv2.imwrite(str(out/"joe_farm13859_source_to_NAIP_overlay.jpg"),image,[cv2.IMWRITE_JPEG_QUALITY,84])
  cv2.imwrite(str(out/"joe_farm13859_reference_aerial.jpg"),best["img"],[cv2.IMWRITE_JPEG_QUALITY,82])
else:qa["status"]="NO_VALID_IMAGE_MATCH_IN_SEARCH_REGION"
(out/"joe_correct_enrolled_farm_registration_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
print("JOE_FARM13859_FINAL",qa["status"],qa.get("inliers"),"tiles",loaded,flush=True)
