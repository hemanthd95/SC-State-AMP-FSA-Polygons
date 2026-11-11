#!/usr/bin/env python3
"""Batch2 Joe Hilliard correct Farm13859 / Tract45814 SOURCE Field36, 25.32 ac.
Photographed 2024 source page independently NAIP-registered with 83 SIFT
inliers. Year2 selected Field20 is NOT on this supplied source photo,
therefore farmer remains open. Other Joe Farm6528 is not substituted.
"""
from pathlib import Path
import math,json,csv,zipfile,io,tempfile,requests,shutil
import cv2,numpy as np,shapefile
from shapely.geometry import Polygon,shape,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as atlas
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/recovery49_batch2_five_20261111"
Z=ROOT/"deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip"
GEO=ROOT/"geojson/counties/recovery49_batch2_joe_hilliard_farm13859_source_field36_20261111.geojson"
GEO.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(Z) as old:
 for rec in old.infolist():
  if rec.is_dir():continue
  file=ROOT/"deliverables"/rec.filename
  file.parent.mkdir(parents=True,exist_ok=True)
  file.write_bytes(old.read(rec))
q=json.loads((ROOT/"analysis/recovery49_20261111/batch2/joe_enrolled_farm13859_registration/joe_correct_enrolled_farm_registration_QA.json").read_text())
assert q["status"]=="SOURCE_FARM13859_GEOREGISTERED_FIELD20_ABSENT"
assert q["source_farm"]=="13859" and q["source_tract"]=="45814"
assert q["inliers"]>=75 and q["rmse_px"]<1.5
assert q["provider"]=="USGS_NAIP"
# Original photographed PDF page rendered to 612 x 792 (page point pixels);
# Field36 bounded by white FSA lines, northern edge shared with Field35,
# eastern edge with timber, lower irregular edge at 358,440.
trace=[(280,330),(385,280),(434,378),(358,440)]
H=np.asarray(q["source_pdf_pts_to_tile_H"],dtype=np.float64)
pix=cv2.perspectiveTransform(np.float32(trace)[None],H)[0]
b=q["bbox_epsg3857"];S=q["tile_size_px"];R=6378137.0
coords=[]
for u,v in pix:
 x=b[0]+float(u)/S*(b[2]-b[0])
 y=b[3]-float(v)/S*(b[3]-b[1])
 coords.append([math.degrees(x/R),math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)])
g=Polygon(coords);assert g.is_valid and not g.is_empty
geod=Geod(ellps="WGS84")
ac=abs(geod.geometry_area_perimeter(g)[0])/4046.8564224
source_ac=25.32
dif=100*(ac/source_ac-1)
assert abs(dif)<25,(ac,dif)
r=requests.get("https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip",timeout=75)
r.raise_for_status()
with tempfile.TemporaryDirectory() as td:
 with zipfile.ZipFile(io.BytesIO(r.content)) as c:c.extractall(td)
 rr=shapefile.Reader(str(next(Path(td).glob("*.shp"))))
 counties=[rec.as_dict()["NAME"] for geom,rec in zip(rr.shapes(),rr.records())
  if rec.as_dict().get("STATEFP")=="45" and shape(geom.__geo_interface__).covers(g.representative_point())]
assert len(counties)==1,counties
county=counties[0]
properties=dict(producer="Joe Hilliard",county=county,roster_county="Orangeburg",
 farm_id="13859",tract_id="45814",field_id="36",fsa_printed_acres=source_ac,
 geodesic_acres=round(ac,4),area_difference_pct=round(dif,2),
 source_pdf="Joe_Hillard_FSA_Map.pdf",source_page=1,source_map_year=2024,
 source_workbook_field_match=False,
 registered_provider="USGS_NAIP",image_registration_inliers=q["inliers"],
 registration_rmse_px=round(q["rmse_px"],3),
 registration_method="83-feature SIFT FSA photographed page to independent NAIP orthophoto",
 physical_county_basis="2025 U.S. Census county polygon; FSA administrative county ignored",
 status="FARM_TRACT_MATCH_SOURCE_FIELD36_BUT_YEAR2_FIELD20_ABSENT",
 geometry_quality="FSA_PHOTO_APPROXIMATE_NOT_SURVEY",
 note="Original source photo shows Field35 33.90ac, Field36 25.32ac, Field37 approx 0.9ac. Year2 target Field20 missing, DO NOT mark farmer completed.")
feature=dict(type="Feature",properties=properties,geometry=mapping(g))
GEO.write_text(json.dumps(dict(type="FeatureCollection",features=[feature]),indent=2)+"\n")
atlas.OUT=OUT
mapqa=atlas.process(("Joe Hilliard",county),[feature])
assert mapqa["county_map_status"]=="CREATED" and mapqa["field_map_status"]=="CREATED"
folder=OUT/county/atlas.human_folder("Joe Hilliard")
(folder/"SOURCE_FARM_MATCH_FIELD20_ABSENT_QA.json").write_text(json.dumps(dict(
 source_map="2024 Farm13859/Tract45814/Field36",source_fsa_acres=source_ac,
 mapped_geodetic_acres=round(ac,4),difference_pct=round(dif,2),
 source_match_inliers=q["inliers"],registration_rmse_px=q["rmse_px"],
 year2_target="13859/45814/20",year2_field20_verified=False,
 administrative_completion=False,map_qa=mapqa),indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "Joe Hilliard 2024 FSA map Farm13859/Tract45814 Field36 (25.32 acres): SOURCE GEOREGISTERED.\n"
 f"Approximate geodesic trace {ac:.3f} acres ({dif:+.1f}%); 83 NAIP image correspondences; 1.18px RMSE.\n"
 "Year2 target Field20 is absent from both available Joe FSA maps. FARMER REMAINS OPEN.\n"
 "Field36 must not be relabeled as Field20. Other supplied map Farm6528 is separate.\n"
 "One EPSG:4326 farmer source shapefile, one topo county map and one satellite field map.\n"
 "This field is a photo-traced research approximation, NOT a legal survey.\n")
old=OUT/"SOURCE_REVIEW_ONLY"/"L-Joe_Hilliard"
if old.exists():shutil.rmtree(old)
csvpath=OUT/"Batch2_Five_Farmer_QA.csv"
with csvpath.open() as f:rows=list(csv.DictReader(f))
for rec in rows:
 if rec["farmer"]=="Joe Hilliard":
  rec.update(status="SOURCE_FARM13859_GEOREGISTERED_BUT_YEAR2_FIELD20_ABSENT",
   accepted_polygon_count="1",physical_county=county,
   target="SOURCE 13859/45814/36 (Year2 13859/45814/20 remains missing)",
   area_ac=str(round(ac,4)),source_registration="83 NAIP matches, 1.18px",
   administratively_closed="False",
   blocker="Source Field36 mapped; Year2 Field20 is absent and remains unverified")
with csvpath.open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]))
 writer.writeheader();writer.writerows(rows)
summary_path=OUT/"BUILD_SUMMARY.json"
s=json.loads(summary_path.read_text())
s["source_review_only"]=2
s["geographically_mapped_source_producers"]=3
s["year2_farmers_geographically_mapped"]=1
s["admin_closed"]=1
s["remaining_followup_farmers_from_44"]=43
s["additional_source_only_fields"]=s.get("additional_source_only_fields",[])+["Joe Hilliard 13859/45814/36"]
s["joe_hilliard_note"]="Correct enrolled Farm13859/Tract45814 source now registered, but only source Fields35/36/37 shown. Field20 remains missing; farmer NOT CLOSED."
s["mappable_source_rows"]=rows
summary_path.write_text(json.dumps(s,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "SC State AMP Batch2 five-farmer GIS: Christine Berry Zeigler complete known Year2 field.\n"
 "Tywone Hilliard has three non-enrolled 2024 source fields mapped; Year2 Farms1064/3826 missing.\n"
 "Joe Hilliard has one SOURCE field (Farm13859/Tract45814/Field36) mapped; Year2 Field20 missing.\n"
 "Calvin Blair and Javeiann Spann locations not accepted. Follow-up queue 43, down from 44.\n"
 "All polygons approximate FSA photo traces; NOT legal surveys.\n")
with zipfile.ZipFile(Z,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as zipout:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():zipout.write(p,p.relative_to(OUT.parent))
with zipfile.ZipFile(Z) as z:
 assert sum(p.endswith(".shp") for p in z.namelist())==3
 assert sum(p.endswith("-FieldMap.pdf") for p in z.namelist())==3
print("BATCH2_JOE_SOURCE_GEOREGISTERED",json.dumps(dict(
 source_farm="13859",tract="45814",field="36",acres=round(ac,4),
 printed=25.32,delta_pct=round(dif,2),county=county,
 map_pages=mapqa["field_map_pages"],mapqa=mapqa,archive_bytes=Z.stat().st_size,
 year2_target_field20_completed=False)),flush=True)
