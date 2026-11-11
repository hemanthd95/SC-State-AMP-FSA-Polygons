#!/usr/bin/env python3
"""Four priority open FSA Farm IDs. Match original imagery to NAIP/Esri.
No polygon is accepted without later source-field trace+acreage validation.
The actual source-photo location takes precedence over administrative county.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,traceback,math,requests,cv2,numpy as np
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/wave1"
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT.mkdir(parents=True,exist_ok=True)
# Anchors are existing separately mapped FSA fields or a user-drawn farm area,
# with Excel farm address as alternate search center, NEVER automatically
# assumed to be true farm location.
CASES=[
 dict(name="John Brabham",source="John Henry Brabham_FSA_Map.pdf",page=2,
      target="3524/3531/25",fsa_area_ac=10.20,
      anchors=[("USER_QGIS_FARM_AREA",-81.04716,33.23855),
               ("EXCEL_ADDRESS",-81.6563,33.7577)]),
 dict(name="Shane Middleton",source="Shane Middleton_FSA Map.pdf",page=2,
      target="9387/8069/7;9387/8069/11",fsa_area_ac=None,
      anchors=[("PREVIOUS_FARM14118",-80.2450,33.3606),
               ("EXCEL_ADDRESS",-80.2427,33.3706)]),
 dict(name="John Lloyd",source="John_Lloyd_FSA_Map.pdf",page=2,
      target="4273/33795/5",fsa_area_ac=None,
      anchors=[("PREVIOUS_FARM4198",-79.9495,33.1700),
               ("PREVIOUS_FARM3756",-79.9349,33.1880),
               ("EXCEL_ADDRESS",-79.93443,33.18779)]),
 dict(name="Margaret Berry",source="Margaret_Berry_FSA_Map.pdf",page=3,
      target="10939/43399/3",fsa_area_ac=1.57,
      anchors=[("PREVIOUS_FARM11782",-80.6505,33.4230),
               ("EXCEL_ADDRESS",-80.65094,33.42136)])
]
SIZE=900
M=1400.;STEP=650.
URLS=core.SERVICES
def fetch(provider,lon,lat,dx,dy):
    mx,my=core.xy(lon,lat)
    mx+=dx*STEP;my+=dy*STEP
    bbox=[mx-M/2,my-M/2,mx+M/2,my+M/2]
    params=dict(bbox=",".join(f"{v:.2f}" for v in bbox),bboxSR=3857,imageSR=3857,
            size=f"{SIZE},{SIZE}",format="jpg",f="image")
    try:
        r=requests.get(URLS[provider],params=params,timeout=22)
        r.raise_for_status()
        tile=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
        if tile is not None and tile.shape[:2]==(SIZE,SIZE):return tile,bbox
    except Exception as exc:pass
    return None
def match(t):
    folder=OUT/t["name"].replace(" ","_")
    folder.mkdir(exist_ok=True)
    views=core.source_views(SRC/t["source"],t["page"])
    if not views:return dict(name=t["name"],status="NO_SOURCE_IMAGE_FEATURES")
    # 17 tiles per center near the nearest previous field,
    # with address fallback if separate. Limit modestly to avoid unbounded scans.
    offsets=[(0,0),(1,0),(-1,0),(0,1),(0,-1),
      (1,1),(1,-1),(-1,1),(-1,-1),(2,0),(-2,0),(0,2),(0,-2)]
    tasks=[(p,lon,lat,dx,dy,anchor) for anchor,lon,lat in t["anchors"]
           for p in ["USGS_NAIP","ESRI_World"] for dx,dy in offsets]
    best=None;loaded=0
    def job(item):
        p,lon,lat,dx,dy,anchor=item
        return item,fetch(p,lon,lat,dx,dy)
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures=[pool.submit(job,t) for t in tasks]
        for future in as_completed(futures):
            try:item,ans=future.result()
            except Exception:continue
            if ans is None:continue
            loaded+=1
            img,bbox=ans
            for view in views:
                m=core.register(view,img)
                if m is None:continue
                scored=(bool(m["valid"]),m["score"])
                if best is not None and scored<=best["scored"]:continue
                best=dict(m=m,view=view,tile=img,bbox=bbox,
                          scored=scored,task=item)
                print("CANDIDATE",t["name"],item[-1],"inliers",m["inliers"],
                      "rmse",round(m["rmse"],2),"valid",m["valid"],flush=True)
    out=dict(name=t["name"],source=t["source"],page=t["page"],
       target_farm_tract_fields=t["target"],fsa_area_acres=t["fsa_area_ac"],
       imagery_tiles_requested=len(tasks),imagery_tiles_loaded=loaded)
    if best is None:
        out["status"]="NO_DEFENSIBLE_IMAGE_MATCH"
    else:
        m=best["m"];view=best["view"]
        H=m["H"]@view["T"];H/=H[2,2]
        p,lon,lat,dx,dy,anchor=best["task"]
        out.update(status="CANDIDATE_NEEDS_FIELD_TRACE_AND_QA" if m["valid"]
             else "WEAK_MATCH_REJECTED",
             inliers=m["inliers"],rmse_px=round(m["rmse"],3),
             valid_geometric_match=bool(m["valid"]),
             source_inlier_spread_px=m["spread_src"],
             target_inlier_spread_px=m["spread_dst"],
             source_pdf_page_points_to_naip_tile_H=H.tolist(),
             tile_bbox_epsg3857=best["bbox"],tile_size_px=SIZE,
             anchor_name=anchor,anchor_lonlat=[lon,lat],
             tile_offset=[dx,dy],imagery_provider=p)
        src=view["crop"];img=best["tile"]
        mask=cv2.warpPerspective(np.full(src.shape[:2],255,dtype=np.uint8),m["H"],(SIZE,SIZE))
        warped=cv2.warpPerspective(src,m["H"],(SIZE,SIZE))
        overlay=cv2.addWeighted(img,.52,warped,.48,0);overlay[mask==0]=img[mask==0]
        cv2.imwrite(str(folder/"candidate_registration_overlay.jpg"),overlay,
                    [cv2.IMWRITE_JPEG_QUALITY,83])
        cv2.imwrite(str(folder/"registered_aerial_tile.jpg"),img,
                    [cv2.IMWRITE_JPEG_QUALITY,82])
    (folder/"registration_qa.json").write_text(json.dumps(out,indent=2)+"\n")
    print("WAVE1_RESULT",t["name"],out["status"],out.get("inliers"),flush=True)
    return out
def main():
    records=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        future={pool.submit(match,t):t for t in CASES}
        for ft in as_completed(future):
            try:result=ft.result()
            except Exception as e:
                result=dict(name=future[ft]["name"],status="ERROR",
                    exception=str(e),traceback=traceback.format_exc()[-1300:])
            records.append(result)
            (OUT/"wave1_batch_summary.json").write_text(json.dumps(records,indent=2)+"\n")
    print("WAVE1_TOTAL",len(records),"STRONG_MATCHES",
          sum(x.get("valid_geometric_match",False) for x in records),flush=True)
if __name__=="__main__":main()
