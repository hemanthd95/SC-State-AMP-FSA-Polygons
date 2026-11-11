#!/usr/bin/env python3
"""Batch2 multi-page FSA aerial registration, independent NAIP feature matching.
Search centers: geocoded Excel addresses and *known* old mapped fields.
Photo matches are not accepted FSA crop boundaries until exact source
Farm/Tract/Field IDs are separately verified and traced.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,math,traceback,requests,cv2,numpy as np,fitz
import recovery7_aerial_registration_20261110 as core
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT=ROOT/"analysis/recovery49_20261111/batch2/source_page_registration"
OUT.mkdir(parents=True,exist_ok=True)
S=900;SPAN=1750.;STEP=700.
AGENT={"User-Agent":"SCStateAMP-Batch2/2026 research farm field registration"}
def geocode(address):
 try:
  d=requests.get("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
      params={"address":address,"benchmark":"Public_AR_Current","vintage":"Current_Current","format":"json"},
      headers=AGENT,timeout=18).json()
  hits=d.get("result",{}).get("addressMatches",[])
  if hits:
   return [dict(source="VERIFIED_CENSUS_ADDRESS_SEARCH_ONLY",lon=x["coordinates"]["x"],lat=x["coordinates"]["y"]) for x in hits[:2]]
 except Exception as e:print("CENSUS_ERROR",address,str(e)[:70],flush=True)
 return []
def old_anchor(name):
 if name not in ("Tywone Hilliard","Christine Berry Zeigler"):return []
 paths=["geojson/orangeburg_registered_fields.geojson",
        "geojson/counties/margaret_berry_farm10939_field3_registered_20261111.geojson"]
 out=[]
 from shapely.geometry import shape
 for path in paths:
  f=ROOT/path
  if not f.exists():continue
  for rec in json.loads(f.read_text())["features"]:
   prod=str(rec.get("properties",{}).get("producer",""))
   allow=((name=="Tywone Hilliard" and prod=="Tywone Hilliard") or
          (name=="Christine Berry Zeigler" and prod in ("Margaret Berry","Mageret Berry")))
   if not allow:continue
   p=shape(rec["geometry"]).representative_point()
   out.append(dict(source="PREVIOUSLY_GEOREGISTERED_NEARBY_FIELD_AS_SEARCH_ONLY",
      lon=p.x,lat=p.y))
 return out[:2]
CASES=[
 dict(name="Joe Hilliard",address="157 Hollis Rd Santee SC 29142",
   enrolled=["13859/45814/20"],sources=["Joe Hillard_FSA_Map.pdf","Joe_Hillard_FSA_Map.pdf"]),
 dict(name="Calvin Blair",address="1033 Armour Hill Dr Pinewood SC 29125",
   enrolled=["3603/848/3"],sources=["Calvin_Blair_FSA_Map.pdf"]),
 dict(name="Tywone Hilliard",address="157 Hollis Rd Santee SC 29142",
   enrolled=["1064/3623","3826/3624"],
   sources=["Tywone Hillard_FSA_Map.pdf","Timothy J Hilliard_FSA_Map.pdf"]),
 dict(name="Christine Berry Zeigler",address="568 Nassau Drive Bowman SC 29018",
   enrolled=["1271/469/1"],sources=["Christine Berry Zeigler_FSA Map.pdf"])
]
# Prioritize closest known registered field (never claim it is enrolled property).
OFFSETS=[(x,y) for x in range(-3,4) for y in range(-3,4)]
OFFSETS.sort(key=lambda d:d[0]**2+d[1]**2)
def fetch(lon,lat,dx,dy,provider):
 mx,my=core.xy(lon,lat);mx+=STEP*dx;my+=STEP*dy
 bbox=[mx-SPAN/2,my-SPAN/2,mx+SPAN/2,my+SPAN/2]
 params=dict(bbox=",".join(f"{v:.3f}" for v in bbox),bboxSR=3857,imageSR=3857,
       size=f"{S},{S}",format="jpg",f="image")
 try:
  r=requests.get(core.SERVICES[provider],params=params,headers=AGENT,timeout=24)
  r.raise_for_status()
  img=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
  if img is not None and img.shape[:2]==(S,S):return img,bbox
 except Exception:pass
 return None
def run(case):
 folder=OUT/case["name"].replace(" ","_")
 folder.mkdir(exist_ok=True)
 anchors=old_anchor(case["name"])+geocode(case["address"])
 # Deduplicate 400m+ separation; never place a field at an address.
 chosen=[]
 for a in anchors:
  if not any(math.hypot((a["lat"]-b["lat"])*111000,
     (a["lon"]-b["lon"])*93000)>0 and math.hypot((a["lat"]-b["lat"])*111000,
     (a["lon"]-b["lon"])*93000)<400 for b in chosen):chosen.append(a)
 result=dict(farmer=case["name"],excel_address=case["address"],
  fsa_enrolled_identifiers=case["enrolled"],
  anchors=chosen,results=[],source_candidates=case["sources"])
 for src in case["sources"]:
  d=fitz.open(SOURCE/src);n=len(d);d.close()
  for pg in range(1,min(4,n)+1):
   try:views=core.source_views(SOURCE/src,pg)
   except Exception as e:
    result["results"].append(dict(pdf=src,page=pg,status="PAGE_READ_ERROR",error=str(e)));continue
   if not views:
    result["results"].append(dict(pdf=src,page=pg,status="NO_IMAGE_FEATURES"));continue
   best=None;loaded=0
   jobs=[(a,p,dx,dy) for a in chosen[:2] for p in ("USGS_NAIP","ESRI_World")
         for dx,dy in OFFSETS[:25]]
   with ThreadPoolExecutor(max_workers=9) as pool:
    futs={pool.submit(fetch,a["lon"],a["lat"],dx,dy,p):(a,p,dx,dy) for a,p,dx,dy in jobs}
    for f in as_completed(futs):
     try:tile=f.result()
     except Exception:tile=None
     if tile is None:continue
     loaded+=1
     a,p,dx,dy=futs[f];im,bbox=tile
     for view in views:
      m=core.register(view,im)
      if m is None:continue
      rank=(bool(m["valid"]),float(m["score"]))
      if best is None or rank>best["rank"]:
       best=dict(m=m,v=view,rank=rank,im=im,bbox=bbox,anchor=a,provider=p,dx=dx,dy=dy)
   record=dict(pdf=src,source_page=pg,tile_requests=len(jobs),tiles_loaded=loaded)
   if not best:
    record["status"]="NO_IMAGE_MATCH"
   else:
    m=best["m"];v=best["v"];H=m["H"]@v["T"];H/=H[2,2]
    accepted=m["valid"] and m["inliers"]>=35 and m["rmse"]<2
    record.update(status="REGISTERED_SOURCE_PHOTO_NEEDS_FIELD_ID_AND_TRACE" if accepted else "WEAK_MATCH_NOT_ACCEPTED",
     valid=bool(accepted),inliers=m["inliers"],rmse_px=round(m["rmse"],4),
     source_spread=m["spread_src"],target_spread=m["spread_dst"],
     source_page_pdf_pts_to_tile_H=H.tolist(),tile_bbox_epsg3857=best["bbox"],
     tile_size_px=S,provider=best["provider"],geocode_anchor=best["anchor"],
     tile_offset=[best["dx"],best["dy"]])
    if accepted:
     prefix=(Path(src).stem.replace(" ","_")[:25]+f"_p{pg}")
     src_img=v["crop"]
     warped=cv2.warpPerspective(src_img,m["H"],(S,S))
     mask=cv2.warpPerspective(np.full(src_img.shape[:2],255,np.uint8),m["H"],(S,S))
     overlay=cv2.addWeighted(best["im"],.55,warped,.45,0);overlay[mask==0]=best["im"][mask==0]
     cv2.imwrite(str(folder/(prefix+"_registration_overlay.jpg")),overlay,[cv2.IMWRITE_JPEG_QUALITY,84])
     cv2.imwrite(str(folder/(prefix+"_aerial_tile.jpg")),best["im"],[cv2.IMWRITE_JPEG_QUALITY,84])
   result["results"].append(record)
   print("BATCH2_MATCH",case["name"],src,pg,record["status"],record.get("inliers"),record.get("rmse_px"),flush=True)
   (folder/"source_registration_QA.json").write_text(json.dumps(result,indent=2)+"\n")
 return result
def main():
 results=[]
 with ThreadPoolExecutor(max_workers=2) as pool:
  futures={pool.submit(run,case):case for case in CASES}
  for f in as_completed(futures):
   try:record=f.result()
   except Exception as e:record=dict(farmer=futures[f]["name"],status="ERROR",error=str(e),traceback=traceback.format_exc()[-900:])
   results.append(record)
   (OUT/"batch2_registration_summary.json").write_text(json.dumps(results,indent=2)+"\n")
 print("BATCH2_REGISTERED_PHOTO_PAGES",sum(sum(r.get("valid",False) for r in x.get("results",[])) for x in results),flush=True)
if __name__=="__main__":main()
