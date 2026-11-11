#!/usr/bin/env python3
"""Jasper Summers: add Year2 missing Farm13709 Tract45514 FSA Fields 8 and 17
to previously registered Farm13653 Field1. Keep Year2 completion unresolved
because roster has a blank field selection and remaining Farm13709 tract45512
has unregistered source pages.
"""
from pathlib import Path
import json,math,zipfile
import cv2,numpy as np
from pyproj import Geod
from shapely.geometry import Polygon,mapping
import publish_per_farmer_weekley_style_20261110 as pub
ROOT=Path(__file__).resolve().parents[1]
Q=ROOT/"analysis/recovery49_20261111/wave4/Jasper_Summers/registration_qa.json"
PREV=ROOT/"geojson/orangeburg_registered_fields.geojson"
GEO=ROOT/"geojson/counties/jasper_summers_farm13709_tract45514_fields8_17_registered_20261111.geojson"
OUT=ROOT/"deliverables/jasper_summers_updated_20261111"
ZIP=ROOT/"deliverables/Jasper_Summers_Expanded_Three_Field_GIS_20261111.zip"
GEO.parent.mkdir(parents=True,exist_ok=True);OUT.mkdir(parents=True,exist_ok=True)
q=json.loads(Q.read_text())
assert q["valid_geometric_match"] and q["inliers"]>=70 and q["rmse_px"]<1
assert q["source_pdf"]=="Jasper Summers FSA Map.pdf"
G=Geod(ellps="WGS84")
R=6378137.;bb=q["tile_bbox_epsg3857"];SIDE=q["tile_size_px"]
H=np.array(q["source_pdf_page_points_to_tile_H"],np.float64)
traces=[
 dict(id="8",acres=4.70,points=[(157,539),(267,260),(296,290),(334,319),
 (405,342),(431,355),(405,401),(389,426),(382,461),(362,497),(328,519),(241,548)]),
 dict(id="17",acres=2.92,points=[(674,311),(675,589),(584,584),(541,419),(552,398)]),
]
new=[]
for t in traces:
 px=np.float32([[(x/796)*612,(y/1030)*792] for x,y in t["points"]])
 warped=cv2.perspectiveTransform(px[None],H)[0]
 coords=[]
 for u,v in warped:
  mx=bb[0]+float(u)/SIDE*(bb[2]-bb[0]);my=bb[3]-float(v)/SIDE*(bb[3]-bb[1])
  coords.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
 p=Polygon(coords)
 assert p.is_valid and not p.is_empty
 acres=abs(G.geometry_area_perimeter(p)[0])/4046.8564224
 diff=100*(acres/t["acres"]-1)
 assert abs(diff)<10,(t["id"],acres,diff)
 props=dict(producer="Jasper Summers",county="Orangeburg",
   amp_roster_county="Orangeburg",farm_id="13709",tract_id="45514",
   field_id=t["id"],fsa_printed_acres=t["acres"],geodesic_acres=round(acres,4),
   percent_area_difference=round(diff,2),
   source_pdf="Jasper Summers FSA Map.pdf",source_page=1,
   source_workbook_field_match="UNDETERMINED_MASTER_HAS_NO_SELECTED_FIELD_ID",
   image_registration_inliers=q["inliers"],image_registration_rmse_px=q["rmse_px"],
   registration_method="SIFT NAIP independent aerial match + manual FSA boundary",
   status="SOURCE_FIELD_GEOREGISTERED_YEAR2_SELECTION_NOT_RECONCILED",
   geometry_quality="FSA_SOURCE_TRACE_APPROXIMATE_NOT_SURVEY")
 new.append({"type":"Feature","properties":props,"geometry":mapping(p)})
 print("JASPER_SOURCE_FIELD",t["id"],"FSA",t["acres"],"computed",acres,"diff",diff,flush=True)
GEO.write_text(json.dumps({"type":"FeatureCollection","features":new},indent=2)+"\n")
old=json.loads(PREV.read_text())["features"]
previous=[f for f in old if f.get("properties",{}).get("producer")=="Jasper Summers"
    and str(f["properties"].get("farm_id"))=="13653"]
assert len(previous)==1
allf=previous+new
pub.OUT=OUT
qa=pub.process(("Jasper Summers","Orangeburg"),allf)
assert qa["county_map_status"]=="CREATED" and qa["field_map_status"]=="CREATED"
qa["farmer_completed"]=False
qa["year2_missing_field_identification"]="Roster Farm13709 has field blank; identified source Fields8 and17 total 7.62 acres vs Year2 requested/enrolled 8 acres."
qa["additional_source"]="Farm13709 Tract45512 Fields16 and27 on separate page3 not yet registered"
folder=OUT/"Orangeburg"/pub.human_folder("Jasper Summers")
(folder/"QA_COMPLETION_STATUS.json").write_text(json.dumps(qa,indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "JASPER SUMMERS — Year2 FARM13709 MAPPING EXPANDED, STILL OPEN FOR FIELD RECONCILIATION.\n"
 "Registered Year2 Farm13709 Tract45514 Fields8 (4.70 ac source) and17 (2.92 ac source).\n"
 "Combined FSA source 7.62 ac vs program enrollment 8.0 ac, exact field ID blank on Year2 roster.\n"
 "Also retained existing Farm13653 Tract5515 Field1 validated older source (2.58ac).\n"
 "Unregistered from Farm13709 Tract45512 source page3: Field16 (2.34ac), Field27 (0.20ac).\n"
 "Image registration: USGS NAIP 97 inliers, 0.374px RMSE (page1 only).\n"
 "The FSA printed office county is not used as a geospatial position constraint.\n"
 "All boundaries are approximate FSA photo traces, not surveys.\n")
(OUT/"README_START_HERE.txt").write_text("Jasper Summers: three mapped FSA features; Year2 farmer NOT closed due to missing field selection/extra source tract.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for file in sorted(OUT.rglob("*")):
  if file.is_file():z.write(file,file.relative_to(OUT.parent))
print("JASPER_EXPANDED",len(allf),"features","fieldmap_pages",qa["field_map_pages"],
  "road_label_pass",qa["two_road_names_pass"],"zip",ZIP.stat().st_size,flush=True)
