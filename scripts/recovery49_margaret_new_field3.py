#!/usr/bin/env python3
"""Recover Margaret Berry Farm10939 Tract43399 Field3 from registered FSA PDF.
Combine with previously registered Farm11782 Field13 without suppressing its
74% acreage QA discrepancy. Updated farmer package does NOT claim closure.
"""
import json,math,zipfile
from pathlib import Path
import cv2,numpy as np
from pyproj import Geod
from shapely.geometry import Polygon,mapping,shape
import publish_per_farmer_weekley_style_20261110 as publisher
ROOT=Path(__file__).resolve().parents[1]
QC=ROOT/"analysis/recovery49_20261111/wave1/Margaret_Berry/registration_qa.json"
OLD=ROOT/"geojson/orangeburg_registered_fields.geojson"
GEO=ROOT/"geojson/counties/margaret_berry_farm10939_field3_registered_20261111.geojson"
OUT=ROOT/"deliverables/margaret_berry_20261111"
ZIP=ROOT/"deliverables/Margaret_Berry_Updated_Two_Farm_Weekley_GIS_20261111.zip"
OUT.mkdir(parents=True,exist_ok=True);GEO.parent.mkdir(parents=True,exist_ok=True)
d=json.loads(QC.read_text())
assert d["valid_geometric_match"] and d["inliers"]>=100 and d["rmse_px"]<1.2, "Image-registration gate failed"
H=np.asarray(d["source_pdf_page_points_to_naip_tile_H"],dtype=float)
bbox=d["tile_bbox_epsg3857"];N=d["tile_size_px"];R=6378137.
# Manual trace of the exact Field 3 yellow FSA perimeter on source
# Margaret_Berry_FSA_Map.pdf p3, rendered at 980x1268 pixel reference.
outline=[(398,516),(416,494),(455,496),(480,486),(529,504),
         (561,488),(625,504),(654,552),(601,601),(536,661),
         (468,621),(442,566),(411,557)]
ref_wh=(980,1268);pdf_wh=(612,792)
points=np.float32([[x*pdf_wh[0]/ref_wh[0],y*pdf_wh[1]/ref_wh[1]] for x,y in outline])
tile=cv2.perspectiveTransform(points[None],H)[0]
ll=[]
for x,y in tile:
    mx=bbox[0]+float(x)/N*(bbox[2]-bbox[0])
    my=bbox[3]-float(y)/N*(bbox[3]-bbox[1])
    ll.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
poly=Polygon(ll)
assert poly.is_valid and not poly.is_empty
geod=Geod(ellps="WGS84")
acres=abs(geod.geometry_area_perimeter(poly)[0])/4046.8564224
assert abs(acres/1.57-1)<.1, f"Expected FSA 1.57 ac, got {acres}"
assert -80.68<poly.centroid.x<-80.62 and 33.39<poly.centroid.y<33.46
props=dict(
    producer="Margaret Berry",county="Orangeburg",amp_roster_county="Orangeburg",
    farm_id="10939",tract_id="43399",field_id="3",
    fsa_printed_acres=1.57,traced_geodesic_acres=round(acres,4),
    source_pdf="Margaret_Berry_FSA_Map.pdf",source_page=3,
    registration_provider=d["imagery_provider"],
    image_registration_inliers=d["inliers"],
    registration_rmse_pixels=d["rmse_px"],
    source_method="Manual FSA yellow boundary trace on NAIP-SIFT registered photo, 163 inliers",
    status="SOURCE_FIELD_ID_AND_IMAGE_LOCATION_VALIDATED_APPROXIMATE_NOT_SURVEY",
    geometry_type="RESEARCH_PLANNING_FIELD_FOOTPRINT_NOT_LEGAL_SURVEY",
    acreage_difference_percent=round((acres/1.57-1)*100,3))
feature={"type":"Feature","properties":props,"geometry":mapping(poly)}
GEO.write_text(json.dumps({"type":"FeatureCollection","features":[feature]},indent=2)+"\n")
existing=json.loads(OLD.read_text())["features"]
old=[f for f in existing if str(f["properties"].get("farm_id"))=="11782"
     and str(f["properties"].get("field_id"))=="13"]
assert len(old)==1, "Previous Farm11782 Field13 not uniquely identified"
old=old[0]
old["properties"]["producer"]="Margaret Berry"
old["properties"]["source_producer_spelling"]="Mageret Berry"
old["properties"]["status"]="EXISTING_REGISTERED_FIELD_13_BOUNDARY_AREA_QA_OPEN_74_PERCENT_DISAGREEMENT"
old["properties"]["reported_FSA_area_mismatch"]="Existing source 7.53 ac vs 13.11 ac rough polygon"
allf=[old,feature]
publisher.OUT=OUT
qa=publisher.process(("Margaret Berry","Orangeburg"),allf)
qa["enrolled_farm_ids_geographically_located"]=["10939","11782"]
qa["new_field3_accepted_acres"]=round(acres,4)
qa["farmer_completed"]=False
qa["reason_not_closed"]="Earlier Farm11782 Field13 polygon differs from FSA printed acreage by about 74%; source shape/boundary still requires independent review"
farmer_dir=OUT/"Orangeburg"/"L-Berry, Margaret"
(farmer_dir/"QA_COMPLETION_STATUS.json").write_text(json.dumps(qa,indent=2)+"\n")
(farmer_dir/"README_STATUS_FIRST.txt").write_text(
    "Margaret Berry (also spelled Mageret): TWO mapped Farm IDs; ONE open acreage QA.\n"
    "NEW: Farm10939 Tract43399 Field3 source 1.57ac; independent NAIP registration 163 inliers, 0.872px RMSE; "
      f"geodetic trace {acres:.3f} acres.\n"
    "EXISTING: Farm11782 Tract6230 Field13 previous source 7.53ac vs approx polygon 13.11ac; flagged, NOT accepted as final area.\n"
    "One producer shapefile with both field features; one topo county map; two satellite close-up sheets.\n"
    "Do not mark this farmer COMPLETED until the 11782 discrepancy is resolved.\n"
    "Source map county is not used as a farm location anchor.\n")
(OUT/"README_START_HERE.txt").write_text("Margaret Berry GIS update. Read Orangeburg/L-Berry, Margaret/README_STATUS_FIRST.txt for acreage and completion caveats.\n")
ZIP.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
    for p in OUT.rglob("*"):
        if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("FIELD_10939_ACCEPTED",round(acres,4),"PACKAGE_BYTES",ZIP.stat().st_size,
    "TWO_MAP_PAGES",qa["field_map_pages"],"FARMER_COMPLETED",False,flush=True)
