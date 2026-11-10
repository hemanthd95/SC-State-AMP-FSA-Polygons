#!/usr/bin/env python3
"""Address-first FSA photo to public USGS NAIP/Esri aerial geographic registration.
Diagnostic output only until labeled farm/tract/field source outlines are digitized
and their areas verified. Do NOT substitute the residence address for polygon coordinates.
"""
import json,io,math,os,cv2,fitz,requests,traceback
import numpy as np
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery7_20261110"
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
TARGS=json.loads((OUT/"address_first_anchors.json").read_text())
OUT.mkdir(parents=True,exist_ok=True)
R=6378137.
SPAN=1550.0;STEP=740.0;SIZE=900
SERVICES={
 "USGS_NAIP":"https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage",
 "ESRI_World":"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
}
SIFT=cv2.SIFT_create(nfeatures=3200,contrastThreshold=.009,edgeThreshold=18)
def prepare(src):
 gray=cv2.cvtColor(src,cv2.COLOR_BGR2GRAY)
 return cv2.createCLAHE(clipLimit=2.1,tileGridSize=(8,8)).apply(gray)
def source_views(path,page_number):
 d=fitz.open(path)
 page=d[page_number-1]
 scale=min(1.45,1900/max(page.rect.width,page.rect.height))
 pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
 full=cv2.imdecode(np.frombuffer(pix.tobytes("png"),np.uint8),cv2.IMREAD_COLOR)
 hh,ww=full.shape[:2]
 result=[]
 # Fraction of rendered page, not dependent on original PDF pixel resolution.
 # For photos of printed USGS/FSA maps, avoid the legend and page border.
 for name,(x0,y0,x1,y1) in {
    "map":(.04,.06,.95,.82), "inner":(.09,.11,.90,.73),
    "center":(.16,.17,.88,.67)}.items():
  l,t,r,b=int(ww*x0),int(hh*y0),int(ww*x1),int(hh*y1)
  crop=full[t:b,l:r].copy()
  factor=min(1.0,1200/max(crop.shape[:2]))
  if factor<1:crop=cv2.resize(crop,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
  pts,desc=SIFT.detectAndCompute(prepare(crop),None)
  if desc is None or len(pts)<50:continue
  T=np.array([[factor*scale,0,-factor*l],[0,factor*scale,-factor*t],[0,0,1]],np.float64)
  result.append(dict(name=name,crop=crop,pts=pts,desc=desc,T=T,
     page_number=page_number,scale=float(scale),source_width=ww,source_height=hh))
 d.close()
 return result
def xy(lon,lat):
 return R*math.radians(lon), R*math.log(math.tan(math.pi/4+math.radians(lat)/2))
def from_xy(x,y):
 return math.degrees(x/R),math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)
def tile(anchor,provider,dx,dy):
 lon,lat=anchor["lon"],anchor["lat"]
 x,y=xy(lon,lat);x+=dx*STEP;y+=dy*STEP
 bb=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
 params=dict(bbox=",".join(f"{z:.2f}" for z in bb),bboxSR=3857,imageSR=3857,
     size=f"{SIZE},{SIZE}",format="jpg",f="image")
 try:
  r=requests.get(SERVICES[provider],params=params,timeout=29)
  r.raise_for_status()
  im=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if im is None or im.shape[:2]!=(SIZE,SIZE):return None
  return im,bb
 except Exception:return None
def register(view,im):
 pts0,desc0=view["pts"],view["desc"]
 pts1,desc1=SIFT.detectAndCompute(prepare(im),None)
 if desc1 is None or len(pts1)<40:return None
 pairs=cv2.FlannBasedMatcher(dict(algorithm=1,trees=5),dict(checks=55)).knnMatch(desc0,desc1,k=2)
 good=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<.75*b.distance]
 if len(good)<20:return None
 p=np.float32([pts0[m.queryIdx].pt for m in good]);q=np.float32([pts1[m.trainIdx].pt for m in good])
 H,m=cv2.findHomography(p,q,cv2.USAC_MAGSAC,4,maxIters=5000,confidence=.998)
 if H is None or m is None:return None
 keep=m.ravel().astype(bool);n=int(keep.sum())
 if n<18:return None
 proj=cv2.perspectiveTransform(p[:,None,:],H)[:,0,:]
 rmse=float(np.sqrt(np.mean(np.sum((proj[keep]-q[keep])**2,axis=1))))
 spr0=np.ptp(p[keep],axis=0);spr1=np.ptp(q[keep],axis=0)
 hh,ww=view["crop"].shape[:2]
 quad=np.float32([[[.08*ww,.08*hh],[.92*ww,.08*hh],[.92*ww,.92*hh],[.08*ww,.92*hh]]])
 area=abs(cv2.contourArea(cv2.perspectiveTransform(quad,H)[0]))
 valid=(n>=33 and rmse<3.2 and min(spr0)>120 and min(spr1)>72 and
        1200<area<2200000)
 score=n*(1+min(spr0)/250)*(1+min(spr1)/300)/(1+rmse)
 return dict(H=H,inliers=n,rmse=rmse,spread_src=spr0.tolist(),spread_dst=spr1.tolist(),
   matches=len(good),valid=bool(valid),score=float(score),projected_area_px=float(area))
def process(t):
 name=t["name"]
 slug="".join(c if c.isalnum() else "_" for c in name).strip("_")
 folder=OUT/slug;folder.mkdir(exist_ok=True)
 src=SRC/t["source_pdf"]
 if not src.exists():return dict(name=name,status="SOURCE_MISSING")
 views=[]
 for page in t["pages"]:
  views.extend(source_views(src,page))
 if not views:return dict(name=name,status="SOURCE_NO_FEATURES")
 # Highest priority: independently geocoded Excel address. Inconsistent
 # workbook points are not used as the center of the farm search.
 addr=[x for x in t["unique_search_anchors"] if x["provider"]!="workbook_coordinate_UNVERIFIED"]
 if not addr:
  addr=[dict(provider="workbook_coordinate_UNVERIFIED",lat=t["workbook_lat"],lon=t["workbook_lon"])]
 addr=addr[:2]
 offsets=[(x,y) for x in range(-2,3) for y in range(-2,3)]
 offsets.sort(key=lambda xy:xy[0]**2+xy[1]**2)
 jobs=[(anchor,provider,dx,dy) for anchor in addr for provider in SERVICES for dx,dy in offsets]
 # A single image tile is tested against *all* page views for the same farmer.
 # Saves bandwidth and avoids choosing an image from the wrong FSA page.
 best={}
 ranked={}
 loaded=0
 print("START",name,"pages",t["pages"],"views",len(views),"tiles",len(jobs),flush=True)
 with ThreadPoolExecutor(max_workers=9) as pool:
  futures={pool.submit(tile,*job):job for job in jobs}
  for future in as_completed(futures):
   anchor,provider,dx,dy=futures[future]
   try:result=future.result()
   except Exception:result=None
   if result is None:continue
   loaded+=1;im,bbox=result
   for v in views:
    m=register(v,im)
    if not m:continue
    page=v["page_number"]
    winner=best.get(page)
    if winner is None or (m["valid"],m["score"])>(winner["m"]["valid"],winner["m"]["score"]):
     best[page]=dict(m=m,view=v,image=im,bbox=bbox,provider=provider,
                      anchor=anchor,dx=dx,dy=dy)
    ranked[page]=max(ranked.get(page,0),m["inliers"])
 records=[]
 for page in t["pages"]:
  item=dict(name=name,source_pdf=t["source_pdf"],source_page=page,workbook_fields=t["fields"],address=t["address"],
   geocode_anchors=addr,loaded_tiles=loaded,requested_tiles=len(jobs))
  cand=best.get(page)
  if cand:
   v=cand["view"];m=cand["m"]
   T=m["H"]@v["T"];T/=T[2,2]
   diag=dict(inliers=m["inliers"],rmse_px=round(m["rmse"],3),source_spread_px=m["spread_src"],
     target_spread_px=m["spread_dst"],valid=m["valid"],score=m["score"],
     full_pdf_points_to_tile_homography=T.tolist(),tile_bbox_epsg3857=cand["bbox"],
     tile_size_wh=[SIZE,SIZE],provider=cand["provider"],geocode_anchor=cand["anchor"]["provider"],
     matched_offset=[cand["dx"],cand["dy"]],page_scale=v["scale"],
     source_page_render_wh=[v["source_width"],v["source_height"]],source_crop=v["name"])
   item.update(registration=diag,
     status="GEOGRAPHIC_IMAGE_MATCH_CANDIDATE_REQUIRES_MANUAL_FIELD_BOUNDARY_QA" if m["valid"]
     else "WEAK_IMAGE_MATCH_NO_ACCEPTED_REGISTRATION")
   cv2.imwrite(str(folder/f"page_{page}_registration_aerial.jpg"),cand["image"],[cv2.IMWRITE_JPEG_QUALITY,82])
   src_im=cand["view"]["crop"]
   warped=cv2.warpPerspective(src_im,m["H"],(SIZE,SIZE))
   mask=cv2.warpPerspective(np.ones(src_im.shape[:2],np.uint8)*255,m["H"],(SIZE,SIZE))
   overlay=cv2.addWeighted(cand["image"],.55,warped,.45,0)
   overlay[mask==0]=cand["image"][mask==0]
   cv2.imwrite(str(folder/f"page_{page}_registration_overlay.jpg"),overlay,[cv2.IMWRITE_JPEG_QUALITY,78])
   print("MATCH",name,"p",page,"valid",m["valid"],"inliers",m["inliers"],"rmse",round(m["rmse"],2),"provider",cand["provider"],"anchor",cand["anchor"]["provider"],flush=True)
  else:
   item["status"]="NO_IMAGE_MATCH";
   print("NO_MATCH",name,"p",page,"tiles_loaded",loaded,flush=True)
  records.append(item)
 (folder/"registration_diagnostics.json").write_text(json.dumps(records,indent=2)+"\n")
 return dict(name=name,results=records)
def main():
 targets=[x for x in TARGS if x["name"] not in ("Rick Boswell",)]
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  futures={pool.submit(process,t):t for t in targets}
  for ft in as_completed(futures):
   try:rec=ft.result()
   except Exception as exc:
    t=futures[ft]
    rec=dict(name=t["name"],error=str(exc),traceback=traceback.format_exc()[-1000:])
    print("ERROR",rec["name"],str(exc),flush=True)
   results.append(rec)
   (OUT/"registration_batch_summary.json").write_text(json.dumps(results,indent=2)+"\n")
 print("DONE",len(results),"farmers",flush=True)
if __name__=="__main__":main()
