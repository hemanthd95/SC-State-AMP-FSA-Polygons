#!/usr/bin/env python3
"""Accept registered research field polygons only when source ID and acreage pass QA.
Printed FSA county is NEVER used to determine actual physical county.
Workbook field mismatch is preserved without mislabeling.
"""
import json,math,copy
from pathlib import Path
import cv2,numpy as np
from shapely.geometry import Polygon,mapping,shape
from shapely.ops import transform
from pyproj import Geod
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery7_20261110"
TARGETS=json.loads((OUT/"address_first_anchors.json").read_text())
BATCH={x["name"]:x["results"] for x in json.loads((OUT/"registration_batch_summary.json").read_text()) if "results" in x}
GEO=ROOT/"geojson/counties/recovery7_address_registered_20261110.geojson"
R=6378137.0
GEOD=Geod(ellps="WGS84")
# Full-page source pixel vertices were traced by visually following field borders.
# Coordinates reference 857x1109 rendered 612x792 FSA sheets, except the
# photographed Albert image (912x1200). No auto polygon or address buffer.
TRACES=[
 {"farmer":"Angale Johnson","page":1,"farm":"22564","tract":"17265","field":"13",
  "area":2.06,"reference_size":[857,1109],
  "points":[[246,402],[279,412],[333,403],[607,417],[685,409],[661,751],[483,740],[483,632],[246,618]]},
 {"farmer":"Angale Johnson","page":2,"farm":"22564","tract":"17268","field":"2",
  "area":3.40,"reference_size":[857,1109],
  "points":[[188,81],[754,107],[692,911],[509,844],[525,773],[517,725],[410,619],[299,522],[223,402],[164,269],[162,238],[179,178]]},
 {"farmer":"Annette Weekley","page":1,"farm":"4706","tract":"11322","field":"3",
  "area":10.68,"source_only":True,"reference_size":[857,1109],
  "points":[[477,337],[598,335],[646,344],[621,388],[590,441],[551,500],[475,623],[377,582],[309,538],[350,484],[400,409]]},
 {"farmer":"Annette Weekley","page":1,"farm":"4706","tract":"11322","field":"10",
  "area":14.25,"source_only":True,"reference_size":[857,1109],
  "points":[[445,175],[678,300],[647,347],[600,334],[479,337],[309,536],[299,539],[231,610],[186,611],[160,590]]},
 {"farmer":"Francena Ellis","page":1,"farm":"4083","tract":"10683","field":"7",
  "area":1.88,"reference_size":[857,1109],
  "points":[[352,325],[451,389],[432,451],[419,510],[469,577],[432,611],[442,653],[407,690],[301,667],[318,559]]},
 {"farmer":"Francena Ellis","page":1,"farm":"4083","tract":"10683","field":"3",
  "area":2.56,"special":"outer_minus_field7","reference_size":[857,1109],
  "points":[[461,274],[461,467],[535,471],[537,512],[516,563],[431,609],[443,654],[408,724],[269,691],[329,252]]}
]
COUNTY_BY_ADDRESS={"Angale Johnson":"Horry","Annette Weekley":"Hampton",
 "Francena Ellis":"Hampton"}
ENROLLMENT_COUNTY={"Angale Johnson":"Horry","Annette Weekley":"Hampton","Francena Ellis":"Jasper"}
def normalized_geo_polygon(t,reg):
 H=np.array(reg["full_pdf_points_to_tile_homography"],np.float64)
 bb=reg["tile_bbox_epsg3857"];n=reg["tile_size_wh"][0]
 pdfsize=[612,792]
 pts=np.float32([[x/t["reference_size"][0]*pdfsize[0],
                     y/t["reference_size"][1]*pdfsize[1]] for x,y in t["points"]])
 xy=cv2.perspectiveTransform(pts[None],H)[0]
 lonlat=[]
 for u,v in xy:
  x=bb[0]+u/n*(bb[2]-bb[0])
  y=bb[3]-v/n*(bb[3]-bb[1])
  lon=x/R*180/math.pi
  lat=(2*math.atan(math.exp(y/R))-math.pi/2)*180/math.pi
  lonlat.append([lon,lat])
 return Polygon(lonlat)
def area_ac(g):
 if g.geom_type=="Polygon":return abs(GEOD.geometry_area_perimeter(g)[0])/4046.8564224
 return sum(area_ac(q) for q in g.geoms)
def main():
 features=[];reports=[]
 for tr in TRACES:
  name=tr["farmer"];page=tr["page"];rec=next((v for v in BATCH.get(name,[]) if v["source_page"]==page),None)
  row={k:tr[k] for k in ("farmer","farm","tract","field","area","page")}
  row["enrolled_selected_field"]=not tr.get("source_only",False)
  if rec is None or "registration" not in rec:
   row["status"]="NO_REGISTERED_AERIAL_COORDINATES";reports.append(row);continue
  info=rec["registration"]
  validated=bool(info["valid"])
  # A lower-inlier match may be used as *provisional* only when the source
  # shape, independent landmark alignment, geodetic area, and local position pass.
  enough_for_provisional=(name=="Angale Johnson" and
    info["inliers"]>=20 and info["rmse_px"]<1.6
    and min(info["target_spread_px"])>=90 and
    min(info["source_spread_px"])>=150)
  if not (validated or enough_for_provisional):
   row["status"]="IMAGE_MATCH_REJECTED_OR_DEGENERATE";reports.append(row);continue
  pg=normalized_geo_polygon(tr,info)
  if not pg.is_valid or pg.is_empty:
   row["status"]="INVALID_POLYGON";reports.append(row);continue
  if tr.get("special")=="outer_minus_field7":
   inner=next(f for f in TRACES if f["farmer"]=="Francena Ellis" and f["field"]=="7")
   poly_inner=normalized_geo_polygon(inner,info)
   pg=pg.difference(poly_inner)
   if not pg.is_valid:pg=pg.buffer(0)
  size_ac=area_ac(pg)
  pct=100*(size_ac/tr["area"]-1)
  row["geodetic_acres"]=round(size_ac,4)
  row["area_difference_pct"]=round(pct,2)
  row["image_match_inliers"]=info["inliers"]
  row["image_match_rmse_px"]=info["rmse_px"]
  center=pg.representative_point()
  anchor=next(x for x in TARGETS if x["name"]==name)["unique_search_anchors"][0]
  dlat=(center.y-anchor["lat"])*111000
  dlon=(center.x-anchor["lon"])*111000*math.cos(math.radians(center.y))
  dist=math.hypot(dlat,dlon)
  row["distance_from_excel_address_m"]=round(dist,1)
  if abs(pct)>30 or dist>4400:
   row["status"]="AREA_OR_LOCATION_QA_REJECTED";reports.append(row);continue
  qstatus=("SOURCE_VISIBLE_NOT_WORKBOOK_SELECTED" if tr.get("source_only",False)
           else "REGISTERED_WITH_LOWER_INLIER_QA_FLAG" if not validated
           else "REGISTERED_AERIAL_MATCH_APPROXIMATE_NOT_SURVEY")
  props={
   "producer":name,"county":COUNTY_BY_ADDRESS[name],
   "physical_county_basis":"Excel farm address geocoded, image registration independently verified; FSA printed county ignored",
   "amp_roster_county":ENROLLMENT_COUNTY[name],
   "farm_id":tr["farm"],"tract_id":tr["tract"],"field_id":tr["field"],
   "fsa_reported_acres":tr["area"],"geodesic_acres":round(size_ac,4),
   "source_pdf":next(x for x in TARGETS if x["name"]==name)["source_pdf"],
   "source_page":page,"source_workbook_field_match":not tr.get("source_only",False),
   "registered_provider":info["provider"],"registration_inliers":info["inliers"],
   "registration_rmse_px":info["rmse_px"],"area_difference_pct":round(pct,1),
   "status":qstatus,"geometry_quality":"PHOTO_TRACED_APPROXIMATE_NOT_SURVEY",
   "source_attribution":"FSA photo map and USGS NAIP aerial image; no new acreage or registered farm location invented",
   "map_source_date":"2026-11-10"
  }
  if name=="Annette Weekley":props["workbook_field_mismatch"]="Workbook selects Farm4706/Tract11322/Field2, but available source shows fields 3,4,5,8,10, NOT Field2"
  if name=="Francena Ellis":props["county_note"]="Workbook lists Jasper; geocoded field at Browning Gate Rd is geographically in Hampton"
  features.append({"type":"Feature","properties":props,"geometry":mapping(pg)})
  row["status"]=qstatus
  reports.append(row)
 GEO.parent.mkdir(parents=True,exist_ok=True)
 GEO.write_text(json.dumps({"type":"FeatureCollection","name":"recovery7_address_registered_subset_20261110",
   "features":features},indent=2)+"\n")
 (OUT/"accepted_polygon_qa.json").write_text(json.dumps({"rows":reports,"accepted_feature_count":len(features),
    "rule":"Never infer farm boundary from printed FSA county or mere producer address; a scanned source must be geographically registered, then manually traced and checked against FSA acreage."},indent=2)+"\n")
 for a in reports:print("POLYGON_QA",a,flush=True)
 print("ACCEPTED",len(features),"SOURCE_CORRECTNESS",sum(x["properties"]["source_workbook_field_match"] for x in features),flush=True)
if __name__=="__main__":main()
