#!/usr/bin/env python3
"""Lewis Gin, Year 2 Farm4706/Tract11322/Field36, photo verified to USGS NAIP.
Farm/tract shared with Annette Weekley but distinct field ID — one farmer folder.
"""
from pathlib import Path
import json,math,zipfile,requests,tempfile,io
import numpy as np,cv2,shapefile
from shapely.geometry import Polygon,shape,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as pub
ROOT=Path(__file__).resolve().parents[1]
Q=ROOT/"analysis/recovery49_20261111/wave3/Lewis_Gin/registration_qa.json"
OUT=ROOT/"deliverables/lewis_gin_completed_20261111"
GEO=ROOT/"geojson/counties/lewis_gin_farm4706_field36_registered_20261111.geojson"
ZIP=ROOT/"deliverables/Lewis_Gin_Completed_AMP_Farmer_GIS_20261111.zip"
OUT.mkdir(parents=True,exist_ok=True);GEO.parent.mkdir(parents=True,exist_ok=True)
reg=json.loads(Q.read_text())
assert reg["valid_geometric_match"] and reg["inliers"]>=100 and reg["rmse_px"]<1
assert reg["enrolled_farm_tract_field"]=="4706/11322/36"
# Manually digitized outline on FSA source 980x1268:
# Field36 strip separates large Field34 from neighboring Field35.
# Distinct adjoining Field13 near road is NOT included for Lewis.
vertices=[(296,729),(385,592),(532,379),(620,387),(443,642),(331,795)]
H=np.asarray(reg["source_pdf_page_points_to_tile_H"],float)
srcxy=np.float32([[(x/980)*612,(y/1268)*792] for x,y in vertices])
target=cv2.perspectiveTransform(srcxy[None],H)[0]
bb=reg["tile_bbox_epsg3857"];size=reg["tile_size_px"];R=6378137.
coords=[]
for x,y in target:
    mx=bb[0]+float(x)/size*(bb[2]-bb[0])
    my=bb[3]-float(y)/size*(bb[3]-bb[1])
    coords.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
poly=Polygon(coords)
assert poly.is_valid and not poly.is_empty
G=Geod(ellps="WGS84")
acres=abs(G.geometry_area_perimeter(poly)[0])/4046.8564224
diff=100*(acres/5.94-1)
assert abs(diff)<8,(acres,diff)
# Source printed county is not authoritative; intersect actual GPS polygon.
resp=requests.get("https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip",timeout=60)
resp.raise_for_status()
with tempfile.TemporaryDirectory() as td:
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:z.extractall(td)
    sh=shapefile.Reader(str(next(Path(td).glob("*.shp"))))
    physical=[rec.as_dict()["NAME"] for geom,rec in zip(sh.shapes(),sh.records())
       if rec.as_dict().get("STATEFP")=="45" and shape(geom.__geo_interface__).covers(poly.representative_point())]
assert len(physical)==1,physical
county=physical[0]
props=dict(
 producer="Lewis Gin",county=county,amp_roster_county="Hampton",farm_id="4706",
 tract_id="11322",field_id="36",fsa_printed_acres=5.94,
 geodesic_acres=round(acres,4),area_difference_percent=round(diff,2),
 source_pdf="Lewis Gin_FSA Map.pdf",source_page=1,
 source_workbook_field_match=True,
 inlier_count=reg["inliers"],registration_rmse_pixels=reg["rmse_px"],
 aerial_reference=reg["imagery_provider"],
 registration_method="Source FSA aerial image SIFT to geographically registered NAIP",
 physical_county_basis="Independent U.S. Census 2025 county spatial overlay; FSA printed county not used",
 shared_fsa_farm="Farm4706/Tract11322 also used by Annette Weekley; her enrolled field not conflated",
 field_boundary_quality="FSA source image research-traced, not a legal survey",
 status="VALIDATED_SELECTED_FIELD_RESEARCH_GEOMETRY"
 )
feature={"type":"Feature","properties":props,"geometry":mapping(poly)}
GEO.write_text(json.dumps({"type":"FeatureCollection","features":[feature]},indent=2)+"\n")
pub.OUT=OUT
qa=pub.process(("Lewis Gin",county),[feature])
assert qa["county_map_status"]=="CREATED" and qa["field_map_status"]=="CREATED"
assert qa["two_road_names_pass"],qa
folder=OUT/county/pub.human_folder("Lewis Gin")
(folder/"README_COMPLETION_STATUS.txt").write_text(
 f"LEWIS GIN - Year2 Farm4706 Tract11322 Field36 COMPLETED FOR RESEARCH MAPPING\n"
 f"FSA {5.94:.2f} acres; digitized geodetic {acres:.3f} acres; error {diff:+.2f}%.\n"
 f"USGS NAIP registration: {reg['inliers']} SIFT inliers; {reg['rmse_px']} pixel residual.\n"
 "Physical county from independent Census mapping, not USDA FSA office header.\n"
 "Annette Weekley shares farm+tract but this is Lewis's separate enrolled Field36.\n"
 "Field13 appears on original annotated FSA source but is not the Year2 selected Field36.\n"
 "One WGS84 farmer shapefile, county topo PDF, satellite field PDF with 2 named streets.\n"
 "Approximate FSA map shape only, not surveyed property ownership or legal boundary.\n")
(folder/"FINAL_QA.json").write_text(json.dumps(dict(
  closed_against_year2_selected_field=True,accepted_feature_count=1,
  farm_id="4706",tract_id="11322",field_id="36",
  image_registration_inliers=reg["inliers"],
  image_registration_rmse_px=reg["rmse_px"],
  reported_acres=5.94,geodetic_acres=round(acres,4),
  area_difference_percent=round(diff,2),map_qa=qa),indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "Lewis Gin, one-farmer Weekley-style GIS package. Exact Year2 selected FSA Field36 mapped.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
  for p in sorted(OUT.rglob("*")):
   if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("LEWIS_COMPLETED",json.dumps(dict(acres=round(acres,3),
   county=county,delta_pct=round(diff,2),zip_bytes=ZIP.stat().st_size,
   road_labels=qa["named_roads"])),flush=True)
