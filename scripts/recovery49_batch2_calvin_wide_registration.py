#!/usr/bin/env python3
"""One rigorous attempt to locate Calvin Blair's exact FSA Farm3603/Tract848
in a broader address-centered NAIP grid. A source match alone does not create
a field; strong match is handed to source Field3 tracing for QA.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import math,json,requests,cv2,numpy as np,time
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/batch2/calvin_wide_match"
OUT.mkdir(exist_ok=True,parents=True)
src=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP/Calvin_Blair_FSA_Map.pdf"
views=core.source_views(src,1)
assert views
anchor=(-80.436293255423,33.594059411505)
cx,cy=core.xy(*anchor)
M=2000.0;STEP=1500.0;SIDE=930
# Spiral out from actual Excel farm address, up to 10.5 km.
offsets=[(dx,dy) for dx in range(-7,8) for dy in range(-7,8)]
offsets.sort(key=lambda p:p[0]**2+p[1]**2)
AGENT={"User-Agent":"SCStateAMP-ResearchFarm2026/MapRegistration"}
def fetch(job):
 dx,dy,provider=job
 x,y=cx+dx*STEP,cy+dy*STEP
 bb=[x-M/2,y-M/2,x+M/2,y+M/2]
 par=dict(bbox=",".join(f"{a:.2f}" for a in bb),bboxSR=3857,imageSR=3857,
    size=f"{SIDE},{SIDE}",format="jpg",f="image")
 try:
  r=requests.get(core.SERVICES[provider],params=par,headers=AGENT,timeout=28)
  r.raise_for_status()
  img=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if img is not None and img.shape[:2]==(SIDE,SIDE):return img,bb
 except Exception:return None
 return None
def search(provider):
 best=None;loaded=0
 tasks=[(dx,dy,provider) for dx,dy in offsets]
 for start in range(0,len(tasks),45):
  curr=tasks[start:start+45]
  with ThreadPoolExecutor(max_workers=9) as pool:
   future={pool.submit(fetch,x):x for x in curr}
   for ft in as_completed(future):
    try:result=ft.result()
    except Exception:result=None
    if result is None:continue
    loaded+=1;im,bb=result
    for v in views:
     mt=core.register(v,im)
     if mt is None:continue
     rank=(bool(mt["valid"]),mt["score"])
     if best is None or rank>best["rank"]:
      best=dict(m=mt,v=v,im=im,bb=bb,rank=rank,job=future[ft])
      print("BEST",provider,loaded,mt["inliers"],mt["rmse"],mt["valid"],future[ft][:2],flush=True)
  if best is not None and best["m"]["valid"] and best["m"]["inliers"]>=110 and best["m"]["rmse"]<1.3:
   break
 return best,loaded
best=None;loaded=0;providers=[]
for provider in ["USGS_NAIP","ESRI_World"]:
 b,n=search(provider);loaded+=n;providers.append(provider)
 if b and (best is None or b["rank"]>best["rank"]):best=b
 if best and best["m"]["valid"] and best["m"]["inliers"]>=110 and best["m"]["rmse"]<1.3:
  break
status="NO_VALID_GEOGRAPHIC_REGISTRATION"
report=dict(producer="Calvin Blair",target="Farm3603/Tract848/Field3",
 source_fsa_acres=12.50,search_anchor_lonlat=anchor,
 search_radius_max_km=11,imagery_tiles_loaded=loaded,providers=providers,
 rule="Do not accept one plausible field solely from address or acreage")
if best:
 mt=best["m"];v=best["v"]
 H=mt["H"]@v["T"];H/=H[2,2]
 status="STRONG_IMAGE_REGISTRATION_AWAITING_SOURCE_FIELD3_TRACE" if mt["valid"] and mt["inliers"]>=65 and mt["rmse"]<1.5 else "WEAK_OR_DEGENERATE_NOT_ACCEPTED"
 report.update(status=status,image_inliers=mt["inliers"],rmse_px=mt["rmse"],
   source_spread=mt["spread_src"],target_spread=mt["spread_dst"],
   homography_source_pdf_pts_to_tile=H.tolist(),bbox_epsg3857=best["bb"],tile_size_px=SIDE,
   provider=best["job"][2],grid_offset=list(best["job"][:2]))
 if status.startswith("STRONG"):
  warped=cv2.warpPerspective(v["crop"],mt["H"],(SIDE,SIDE))
  mask=cv2.warpPerspective(np.full(v["crop"].shape[:2],255,np.uint8),mt["H"],(SIDE,SIDE))
  overlay=cv2.addWeighted(best["im"],.55,warped,.45,0);overlay[mask==0]=best["im"][mask==0]
  cv2.imwrite(str(OUT/"calvin_registered_FSA_photo_NAIP_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,85])
  cv2.imwrite(str(OUT/"calvin_reference_aerial.jpg"),best["im"],[cv2.IMWRITE_JPEG_QUALITY,82])
else:report["status"]=status
(OUT/"calvin_wide_search_QA.json").write_text(json.dumps(report,indent=2)+"\n")
print("CALVIN_WIDE_RESULT",report["status"],report.get("image_inliers"),"tiles",loaded,flush=True)
