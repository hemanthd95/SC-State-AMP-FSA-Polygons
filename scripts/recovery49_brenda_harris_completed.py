#!/usr/bin/env python3
"""Brenda M. Harris: Farm4943/Tract4414/Field3, independently NAIP-registered
FSA boundary with geodesic acreage and physical-county QA.
Author one individual Weekley-format shapefile and two maps; no ownership claim.
"""
from pathlib import Path
import json,math,zipfile,requests,io,tempfile
import numpy as np,cv2,shapefile
from shapely.geometry import shape,Polygon,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as pub

ROOT=Path(__file__).resolve().parents[1]
Q=ROOT/"analysis/recovery49_20261111/wave3/Brenda_M__Harris/registration_qa.json"
GEOPATH=ROOT/"geojson/counties/brenda_harris_farm4943_field3_verified_20261111.geojson"
OUT=ROOT/"deliverables/brenda_harris_completed_20261111"
ZIP=ROOT/"deliverables/Brenda_M_Harris_Completed_AMP_Farmer_GIS_20261111.zip"
OUT.mkdir(parents=True,exist_ok=True);GEOPATH.parent.mkdir(parents=True,exist_ok=True)
q=json.loads(Q.read_text())
assert q["valid_geometric_match"] and q["inliers"]>=100 and q["rmse_px"]<=1.0
assert q["imagery_provider"]=="USGS_NAIP"
assert q["enrolled_farm_tract_field"]=="4943/4414/3"
# FSA source p1 Field3 inner cropland outline (NOT the encompassing forested tract).
# Trace in 980x1268 rendered reference pixels.
TRACE=[
(209,395),(375,301),(398,295),(415,299),(439,324),
(452,421),(438,470),(427,476),(431,523),(449,525),
(474,572),(489,666),(431,677),(386,714),(315,776),
(308,820),(242,852),(202,865),(171,854),(140,787),
(203,767),(197,641),(182,594),(216,577),(210,507)
]
H=np.asarray(q["source_pdf_page_points_to_tile_H"],dtype=np.float64)
xy=np.float32([[(x/980.)*612.,(y/1268.)*792.] for x,y in TRACE])
pixel=cv2.perspectiveTransform(xy[None],H)[0]
bbox=q["tile_bbox_epsg3857"];side=q["tile_size_px"];R=6378137.
ll=[]
for px,py in pixel:
 x=bbox[0]+float(px)/side*(bbox[2]-bbox[0])
 y=bbox[3]-float(py)/side*(bbox[3]-bbox[1])
 ll.append([math.degrees(x/R),math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)])
p=Polygon(ll)
assert p.is_valid and not p.is_empty
geod=Geod(ellps="WGS84")
acres=abs(geod.geometry_area_perimeter(p)[0])/4046.8564224
delta=100*(acres/19.39-1)
assert abs(delta)<8,("FSA acreage gate failed",acres,delta)
# Official Census 2025 county geometry; never trust header administrative county.
url="https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
resp=requests.get(url,timeout=60);resp.raise_for_status()
with tempfile.TemporaryDirectory() as tmp:
 with zipfile.ZipFile(io.BytesIO(resp.content)) as z:z.extractall(tmp)
 s=shapefile.Reader(str(next(Path(tmp).glob("*.shp"))))
 counties=[rec.as_dict()["NAME"] for geom,rec in zip(s.shapes(),s.records())
          if rec.as_dict().get("STATEFP")=="45" and shape(geom.__geo_interface__).covers(p.representative_point())]
assert len(counties)==1,counties
county=counties[0]
props={
 "producer":"Brenda M. Harris","county":county,"roster_county":"Dorchester",
 "farm_id":"4943","tract_id":"4414","field_id":"3",
 "fsa_printed_acres":19.39,"geodesic_acres":round(acres,4),
 "area_difference_percent":round(delta,2),
 "source_pdf":"Brenda Harris_FSAmap.pdf","source_page":1,
 "source_workbook_field_match":True,
 "registered_provider":"USGS_NAIP",
 "image_registration_inliers":q["inliers"],
 "image_registration_rmse_px":q["rmse_px"],
 "registration_method":"Image feature matching FSA raster to georeferenced NAIP; manual Field3 outline digitization",
 "physical_county_basis":"Official Census 2025 county polygon, ignoring printed FSA map header",
 "geometry_quality":"SOURCE_FIELD_TRACED_APPROXIMATE_NOT_SURVEY",
 "status":"ENROLLED_FIELD_REGISTERED_AND_AREA_QA_PASSED"
}
feature={"type":"Feature","properties":props,"geometry":mapping(p)}
GEOPATH.write_text(json.dumps({"type":"FeatureCollection","features":[feature]},indent=2)+"\n")
pub.OUT=OUT
mapqa=pub.process(("Brenda M. Harris",county),[feature])
assert mapqa["county_map_status"]=="CREATED" and mapqa["field_map_status"]=="CREATED" and mapqa["two_road_names_pass"]
folder=OUT/county/pub.human_folder("Brenda M. Harris")
# Require all 5 essential shapefile pieces
shps=[p for p in folder.rglob("*.shp") if p.is_file()];assert len(shps)==1, shps
for ext in [".dbf",".shx",".prj",".cpg"]:assert shps[0].with_suffix(ext).exists()
qa={"year2_target":"Farm4943/Tract4414/Field3","target_field_mapped":True,
    "farmer_closed_against_known_year2_record":True,
    "calculated_acres":round(acres,4),"fsa_acres":19.39,
    "percent_error":round(delta,2),"registration_inliers":q["inliers"],
    "registration_rmse_pixels":q["rmse_px"],"physical_county":county,
    "map_qa":mapqa,"legal_note":"Approximate FSA field trace, not a survey or ownership assertion"}
(folder/"COMPLETION_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "YEAR2 COMPLETION: Brenda M. Harris, FSA Farm4943, Tract4414, Field3.\n"
 f"Source 19.39 acres; geodesic trace {acres:.3f} acres (difference {delta:+.2f}%).\n"
 f"NAIP feature registration {q['inliers']} inliers, {q['rmse_px']}px residual.\n"
 f"Physical county: {county}; source FSA printed county NOT used as locator.\n"
 "One EPSG:4326 farmer shapefile, one county-topo PDF and one satellite PDF with 2+ named roads.\n"
 "Not a cadastral survey; ground verification before legal/boundary decisions.\n")
(OUT/"README_START_HERE.txt").write_text("Brenda M. Harris enrolled Field3 completed; QA and approximate boundary caveats inside farmer folder.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for f in sorted(OUT.rglob("*")):
  if f.is_file():z.write(f,f.relative_to(OUT.parent))
print("BRENDA_COMPLETED",json.dumps({"acreage":round(acres,3),"physical_county":county,
  "area_difference_pct":round(delta,2),"zip_bytes":ZIP.stat().st_size,
  "road_labels":mapqa["named_roads"]}),flush=True)
