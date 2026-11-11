#!/usr/bin/env python3
"""Batch1 enrichment after independent NAIP registration of additional FSA tracts.
Charles Bright Farm2715/Tract3021 Field4 and Field7; Jasper Summers
Farm13709/Tract45512 Field16 and Field27. Quantitative area QA, no guessed ID.
Retain all previously mapped farmer folders in a single updated Batch1 ZIP.
"""
from pathlib import Path
import json,math,csv,zipfile,shutil
import numpy as np,cv2
from shapely.geometry import Polygon,shape,mapping
from shapely.ops import unary_union
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as atlas

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/"deliverables/batch1_five_farmer_recovery_20261111"
ZIP=ROOT/"deliverables/AMP_Batch1_Five_Farmer_GIS_20261111.zip"
QROOT=ROOT/"analysis/recovery49_20261111/batch1_extra_tracts"
GEO=ROOT/"geojson/counties/recovery49_batch1_extra_tract_fields_20261111.geojson"
GEO.parent.mkdir(parents=True,exist_ok=True)
# Recover all five existing directories from previously delivered ZIP.
with zipfile.ZipFile(ZIP) as z:
 for item in z.infolist():
  if item.is_dir():continue
  p=ROOT/"deliverables"/item.filename
  p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(z.read(item))
assert BASE.is_dir()
R=6378137.;GEOD=Geod(ellps="WGS84")
atlas.OUT=BASE

SPECS=[
 dict(name="Charles Bright Jr.",slug="Charles_Bright_Jr.",county="Colleton",
   farm="2715",tract="3021",page=2,pdf="Bright, Charles, JR_ FSAmap.pdf",
   fields={
    "4":{"acres":3.48,"xy":[(273,352),(284,324),(304,336),(318,359),(338,362),
      (360,358),(372,342),(377,319),(373,278),(401,273),(425,270),
      (428,329),(441,366),(454,413),(467,448),(485,490),(464,493),
      (447,485),(436,465),(430,450),(414,419),(388,405),(357,402),
      (339,406),(324,426),(291,447)]},
    "7":{"acres":30.82,"xy":[(201,269),(459,207),(535,430),(674,401),(771,708),(404,849)]},
   },
   # Inner excluded Field6 yellow boundary is identifiable, but area differs
   # by ~18% from FSA 0.96 ac, so do not accept as an independent field polygon.
   exclude_field6=[(605,429),(674,402),(683,503),(649,513),(629,518),(612,483)],
   source_exceptions="Field6 trace (1.13 vs 0.96 acres) requires boundary review; Tract3022 Fields9/10/3 remain source-only; Year2 field selection blank."),
 dict(name="Jasper Summers",slug="Jasper_Summers",county="Orangeburg",
   farm="13709",tract="45512",page=3,pdf="Jasper Summers FSA Map.pdf",
   fields={
     "16":{"acres":2.34,"xy":[(397,391),(417,391),(438,398),(473,402),
       (493,427),(499,478),(505,530),(505,580),(488,638),(477,682),
       (460,741),(395,734)]},
     "27":{"acres":.20,"xy":[(625,445),(619,558),(608,560),(586,480)]},
   },
   source_exceptions="Year2 master selects Farm13709 but field number blank; source page1 Tract45514 Fields8 and17 already mapped.")
]
def to_poly(points,q):
 H=np.asarray(q["source_pdf_points_to_tile_H"],dtype=float)
 bbox=q["tile_bbox_epsg3857"];side=q["tile_size_px"]
 xy=np.float32([[(x/980)*612,(y/1268)*792] for x,y in points])
 mapped=cv2.perspectiveTransform(xy[None],H)[0]
 coords=[]
 for px,py in mapped:
  x=bbox[0]+float(px)/side*(bbox[2]-bbox[0])
  y=bbox[3]-float(py)/side*(bbox[3]-bbox[1])
  coords.append([math.degrees(x/R),math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)])
 poly=Polygon(coords)
 assert poly.is_valid and not poly.is_empty
 return poly
def acres(g):
 if g.geom_type=="Polygon":return abs(GEOD.geometry_area_perimeter(g)[0])/4046.8564224
 return sum(acres(p) for p in g.geoms)
added=[]
row_append=[]
for s in SPECS:
 q=json.loads((QROOT/s["slug"]/"extra_tract_qa.json").read_text())
 assert q["status"]=="REGISTERED_CANDIDATE_REQUIRES_SOURCE_TRACE_AND_AREA_QA"
 assert q["inliers"]>=100 and q["rmse_px"]<.8 and q["provider"]=="USGS_NAIP"
 folder=BASE/s["county"]/atlas.human_folder(s["name"])
 previous=json.loads((folder/"REGISTERED_FIELDS.geojson").read_text())["features"]
 tracings={fid:to_poly(entry["xy"],q) for fid,entry in s["fields"].items()}
 # The large 30.82ac Charles Field7 source outline contains separate
 # FSA Fields4/6 (interior carve-outs). Subtract both before acreage check.
 if s["name"]=="Charles Bright Jr.":
  excluded6=to_poly(s["exclude_field6"],q)
  area6=acres(excluded6)
  assert area6>.96*1.15, "Field6 exception must remain documented"
  tracings["7"]=tracings["7"].difference(unary_union([tracings["4"],excluded6]))
  assert tracings["7"].is_valid and not tracings["7"].is_empty
 for fid,poly in tracings.items():
  ref=s["fields"][fid]["acres"];size=acres(poly)
  delta=100*(size/ref-1)
  gate=11 if ref>=1 else 10
  assert abs(delta)<gate,(s["name"],fid,ref,size,delta)
  # Keep the original registered field IDs and never substitute Field6 for Field7.
  properties=dict(producer=s["name"],county=s["county"],
    farm_id=s["farm"],tract_id=s["tract"],field_id=fid,
    source_pdf=s["pdf"],source_page=s["page"],
    fsa_reported_acres=ref,geodesic_acres=round(size,4),
    acreage_difference_pct=round(delta,2),
    source_workbook_field_match=False,
    registration_provider=q["provider"],registration_inliers=q["inliers"],
    registration_rmse_px=round(q["rmse_px"],4),
    registration_method="SIFT source photo to geographically referenced USGS NAIP; manual FSA field outline",
    status="REGISTERED_SOURCE_FIELD_YEAR2_ENROLLMENT_SELECTION_OPEN",
    geometry_quality="FSA_PHOTO_TRACE_APPROXIMATE_NOT_SURVEY",
    note=s["source_exceptions"])
  f=dict(type="Feature",properties=properties,geometry=mapping(poly))
  key=(s["farm"],s["tract"],fid)
  assert not any(tuple(str(p["properties"].get(k,"")) for k in
      ("farm_id","tract_id","field_id"))==key for p in previous)
  previous.append(f);added.append(f)
  row_append.append(dict(farmer=s["name"],physical_county=s["county"],
     farm_id=s["farm"],tract_id=s["tract"],field_id=fid,
     fsa_acres=ref,mapped_acres=round(size,4),
     area_delta_pct=round(delta,2),image_matches=q["inliers"],
     image_rmse_px=round(q["rmse_px"],3),
     status="REGISTERED_SOURCE_FIELD_APPROXIMATE",farmer_closed=False,
     notes=s["source_exceptions"]))
  print("EXTRA_FIELD_ACCEPTED",s["name"],fid,round(size,4),"ac",round(delta,2),"%",flush=True)
  # Separate source-registered output layer for reproducibility.
 qa=atlas.process((s["name"],s["county"]),previous)
 assert qa["county_map_status"]=="CREATED" and qa["field_map_status"]=="CREATED"
 assert qa["two_road_names_pass"],qa
 (folder/"BATCH1_EXTRA_TRACT_QA.json").write_text(json.dumps(dict(
   added_fields=[f["properties"] for f in added if f["properties"]["producer"]==s["name"]],
   source_exceptions=s["source_exceptions"],
   registration_inliers=q["inliers"],registration_rmse_px=q["rmse_px"],
   registration_page=s["page"],cartography=qa,
   farmer_completed=False,
   exact_enrollment_selection_verified=False,
   legal_disclaimer="Photo-traced research approximations; not ownership or survey boundary"),indent=2)+"\n")
 (folder/"README_COMPLETION_STATUS.txt").write_text(
   f"{s['name']} - Batch1 extended source mapping\n"
   f"STATUS: SOURCE FIELDS GEOGRAPHICALLY REGISTERED, ENROLLMENT MATCH OPEN.\n"
   f"Included source: {s['farm']} Tract{s['tract']}, page {s['page']}\n"
   f"New source fields: {','.join(s['fields'])}\n"
   f"Remaining exceptions: {s['source_exceptions']}\n"
   "All historical georeferenced fields retained. WGS84 producer shapefile; one county topo map; multiple satellite close-up pages.\n"
   "Printed FSA administrative county not used to locate field. Not a cadastral survey.\n")
 # Refresh individual GIS ZIP for Charles; Jasper retains archive as a complete
 # current combined folder too (original Jasper ZIP remains provenance).
 filename=ROOT/"deliverables"/(s["name"].replace(" ","_").replace(".","")+"_Batch1_GIS_20261111.zip")
 with zipfile.ZipFile(filename,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as zz:
  for p in sorted(folder.rglob("*")):
   if p.is_file():zz.write(p,p.relative_to(BASE))
 print("EXTRA_FARMER_PACKAGE",s["name"],len(previous),qa["field_map_pages"],flush=True)

GEO.write_text(json.dumps({"type":"FeatureCollection",
  "name":"SC_AMP_Batch1_Additional_Tract_Validated_Source_Fields",
  "features":added},indent=2)+"\n")
index=BASE/"Batch1_Farmer_QA.csv"
with index.open() as f:rows=list(csv.DictReader(f))
headers=list(rows[0])
for r in row_append:rows.append({k:str(r.get(k,"")) for k in headers})
with index.open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=headers)
 writer.writeheader();writer.writerows(rows)
summary_path=BASE/"BATCH1_BUILD_SUMMARY.json"
summary=json.loads(summary_path.read_text())
summary["newly_accepted_source_geometries"]=len(json.loads((ROOT/"geojson/counties/recovery49_batch1_source_registered_20261111.geojson").read_text())["features"])+len(added)
summary["additional_registered_source_fields"]=[
  "Charles Bright Jr. 2715/3021/4","Charles Bright Jr. 2715/3021/7",
  "Jasper Summers 13709/45512/16","Jasper Summers 13709/45512/27"]
summary["newly_closed_year2_farmers"]=[]
summary["not_closed"]=summary["participants"]
summary["critical_note"]="All five participants remain YEAR2 enrollment selection or acreage QA open; 4 extra FSA source polygons registered but NO additional farmer closed."
summary_path.write_text(json.dumps(summary,indent=2)+"\n")
(BASE/"README_START_HERE.txt").write_text(
 "SC STATE AMP - BATCH1 FIVE-FARMER GIS (UPDATED WITH ADDITIONAL TRACTS)\n"
 "Charles Bright Jr.: Farm2715/Tract3021 Fields4/7 and Tract3022 Field2, other fields remain unresolved.\n"
 "Joseph Gadson: Farm4547/Tract4482 source Fields3/4 georegistered, enrollment IDs blank.\n"
 "Arthur Cobbs: Farm548/Tract295 Field1 source mapped, enrollment selected Field ID blank.\n"
 "Jasper Summers: Farm13709 Tract45514 Fields8/17 and Tract45512 Fields16/27, plus older Farm13653.\n"
 "Margaret Berry: Farm10939 Field3 and Farm11782 Field13; earlier 74% acreage mismatch unresolved.\n"
 "Zero of five farmers administratively closed; source-registered geometry is not a legal survey.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for f in sorted(BASE.rglob("*")):
  if f.is_file():z.write(f,f.relative_to(BASE.parent))
with zipfile.ZipFile(ZIP) as z:
 paths=z.namelist()
 assert len([p for p in paths if p.endswith("-FieldMap.pdf")])==5
 assert len([p for p in paths if p.endswith(".shp")])==5
 assert len([p for p in paths if p.endswith("-CountyMap.pdf")])==5
print("BATCH1_UPDATED",json.dumps(dict(
 new_extra_fields=len(added),total_new_fields=summary["newly_accepted_source_geometries"],
 total_farmers=5,closed_year2=0,zip_bytes=ZIP.stat().st_size)),flush=True)
