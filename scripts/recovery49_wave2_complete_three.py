#!/usr/bin/env python3
"""Wave 2: finalize three source-label-verified FSA polygons.
Matches must pass USGS NAIP photo registration AND manual yellow/white
FSA field boundary source-label identification AND geodetic acreage QA.
"""
from pathlib import Path
import json,math,zipfile
import cv2,numpy as np
from shapely.geometry import shape,Polygon,Point,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as pub
ROOT=Path(__file__).resolve().parents[1]
QC=ROOT/"analysis/recovery49_20261111/wave2"
GEO=ROOT/"geojson/counties/recovery49_wave2_three_completed_20261111.geojson"
DEST=ROOT/"deliverables/recovery49_wave2_three_20261111"
BUNDLE=ROOT/"deliverables/AMP_Recovery49_Three_Completed_Farmer_GIS_20261111.zip"
GEO.parent.mkdir(parents=True,exist_ok=True);DEST.mkdir(parents=True,exist_ok=True)
SPECS=[
 dict(name="Tiffany Loadholt",roster="Allendale",farm="3779",tract="10394",
  field="54",printed_acres=15.18,source="Tifanny Loadholt_FSA_Map.pdf",
  points=[(286,346),(585,235),(646,524),(541,552),(501,516),(406,577),(386,566),(349,591)]),
 dict(name="Jan Davis Boneparte",roster="Calhoun",farm="3549",tract="8353",
  field="2",printed_acres=7.72,source="Jan Davis-Boneparte_FSA_Map.pdf",
  points=[(344,500),(398,518),(414,542),(458,543),(482,554),(511,588),(560,607),
          (510,743),(218,648),(235,575),(310,600)]),
 dict(name="Eartha Pinckney",roster="Dorchester",farm="6579",tract="22687",
  field="11",printed_acres=5.81,source="Eartha_Pinckney_FSA_Map.pdf",
  points=[(247,500),(360,466),(379,550),(319,560),(280,545),(248,552)])
]
geod=Geod(ellps="WGS84")
counties=json.loads((ROOT/"geojson/sc_counties_for_verified_atlases.geojson").read_text())["features"]
def real_county(geom):
 r=geom.representative_point()
 found=[x["properties"]["NAME"] for x in counties if shape(x["geometry"]).covers(r)]
 if len(found)!=1:raise RuntimeError("Cannot resolve independent physical SC county: "+str(found))
 return found[0]
def convert(s):
 n=s["name"];slug=n.replace(" ","_")
 q=json.loads((QC/slug/"registration_qa.json").read_text())
 assert q["valid_geometric_match"] and q["inliers"]>=65 and q["rmse_px"]<=1.1, "Image QA failed "+n
 H=np.array(q["source_pdf_page_points_to_tile_H"],dtype=float)
 bbox=q["tile_bbox_epsg3857"];side=q["tile_size_px"]
 points=np.float32([[x*612/980,y*792/1268] for x,y in s["points"]])
 xx=cv2.perspectiveTransform(points[None],H)[0]
 R=6378137.0
 coords=[]
 for x,y in xx:
   mx=bbox[0]+float(x)/side*(bbox[2]-bbox[0])
   my=bbox[3]-float(y)/side*(bbox[3]-bbox[1])
   coords.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
 poly=Polygon(coords)
 assert poly.is_valid and not poly.is_empty
 area=abs(geod.geometry_area_perimeter(poly)[0])/4046.8564224
 difference=100*(area/s["printed_acres"]-1)
 if abs(difference)>12:raise RuntimeError(f"FSA acreage disagreement {n}: {difference:.1f}%")
 county=real_county(poly)
 p=dict(
  producer=n,county=county,amp_roster_county=s["roster"],
  farm_id=s["farm"],tract_id=s["tract"],field_id=s["field"],
  fsa_printed_acres=s["printed_acres"],geodesic_area_acres=round(area,4),
  acreage_difference_percent=round(difference,2),
  source_pdf=s["source"],source_page=1,
  source_workbook_field_match=True,
  image_registration_inliers=q["inliers"],image_registration_rmse_pixels=q["rmse_px"],
  georeferenced_provider=q["imagery_provider"],
  registration_method="FSA aerial SIFT homography to independently georeferenced USGS NAIP",
  physical_county_basis="Census county spatial polygon intersects georeferenced field, not printed FSA county",
  geometry_quality="FSA_PHOTO_TRACED_APPROXIMATE_NOT_SURVEY",
  status="FIELD_ID_MATCHED_REGISTERED_AREA_QA_PASSED",
  note="Research/AMP FSA imagery boundary, not legal ownership or a land survey")
 return {"type":"Feature","properties":p,"geometry":mapping(poly)}
features=[convert(s) for s in SPECS]
GEO.write_text(json.dumps({"type":"FeatureCollection","name":"AMP_Recovery49_Three_Validated_20261111",
   "features":features},indent=2)+"\n")
pub.OUT=DEST
for f in features:
   p=f["properties"];name=p["producer"];county=p["county"]
   qa=pub.process((name,county),[f])
   assert qa["field_map_status"]=="CREATED" and qa["county_map_status"]=="CREATED"
   assert qa["two_road_names_pass"],f"Two street labels missing for {name}"
   folder=DEST/county/pub.human_folder(name)
   (folder/"FIELD_COMPLETION_QA.json").write_text(json.dumps({
       "name":name,"farmer_fsa_farm":p["farm_id"],"tract":p["tract_id"],
       "enrolled_field":p["field_id"],"complete_against_year2_single_field_record":True,
       "field_validation":p,"map_qa":qa},indent=2)+"\n")
   (folder/"README_COMPLETION_STATUS.txt").write_text(
       f"{name} - Year2 registered enrolled field: Farm {p['farm_id']} Tract {p['tract_id']} Field {p['field_id']}\n"
       f"USGS NAIP inliers {p['image_registration_inliers']}, residual {p['image_registration_rmse_pixels']:.3f} pixels.\n"
       f"FSA {p['fsa_printed_acres']:.2f} acres vs {p['geodesic_area_acres']:.3f} mapped acres ({p['acreage_difference_percent']:+.1f}%).\n"
       f"Physical county: {county}. FSA office county is NOT a location criterion.\n"
       "EPSG:4326 farmer shapefile + county topo and road-labeled satellite PDFs included.\n"
       "Approximate field geometry for research planning, not a legal survey or claim of ownership.\n")
   individual=ROOT/"deliverables"/(name.replace(" ","_")+"_Completed_AMP_Farmer_GIS_20261111.zip")
   with zipfile.ZipFile(individual,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
       for file in folder.rglob("*"):
         if file.is_file():z.write(file,file.relative_to(DEST))
   print("COMPLETED_FIELD",name,county,p["farm_id"],p["field_id"],
         p["geodesic_area_acres"],"ac",individual.stat().st_size,flush=True)
(DEST/"README_START_HERE.txt").write_text(
 "SC STATE AMP: Three completed Year2 single-field farmers.\n"
 "Tiffany Loadholt (3779/10394/54), Jan Davis Boneparte (3549/8353/2), Eartha Pinckney (6579/22687/11).\n"
 "Completed here means the Year2 selected field identity+georegistration+acreage+map QA pass.\n"
 "All polygons are FSA-photo-derived approximations and are not legal surveys.\n")
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for file in DEST.rglob("*"):
   if file.is_file():z.write(file,file.relative_to(DEST.parent))
print("WAVE2_THREE_COMPLETED",len(features),"BUNDLE_BYTES",BUNDLE.stat().st_size,flush=True)
