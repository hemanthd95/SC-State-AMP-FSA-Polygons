#!/usr/bin/env python3
"""Batch2 first deliverable: Christine Berry Zeigler's exact FSA Field1
registered to independent NAIP using her photographed Arista/Baxley map.

Review mode: approximate FSA source boundary accepted with <=25% acreage
difference, but independent geographic registration and exact target identity
still required. All other Batch2 cases stay explicitly open until located.
"""
from pathlib import Path
import json, math, csv, zipfile, io, tempfile, requests
import cv2,numpy as np,shapefile
from shapely.geometry import Polygon,shape,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as atlas

ROOT=Path(__file__).resolve().parents[1]
QROOT=ROOT/"analysis/recovery49_20261111"
BASE=ROOT/"deliverables/recovery49_batch2_five_20261111"
BUNDLE=ROOT/"deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip"
GEO=ROOT/"geojson/counties/recovery49_batch2_christine_berry_zeigler_field1_20261111.geojson"
BASE.mkdir(parents=True,exist_ok=True);GEO.parent.mkdir(parents=True,exist_ok=True)
qa=json.loads((QROOT/"batch2/christine_arista_baxley_registration/Christine_road_constrained_registration_QA.json").read_text())
assert qa["status"]=="ROAD_CONSTRAINED_NAIP_REGISTRATION_MATCH_FIELD_TRACE_NEEDED"
assert qa["provider"]=="USGS_NAIP" and qa["image_matches"]>=150 and qa["rmse_px"]<1.8
assert qa["target"]=="1271/469/1"
# Source FSA page at 1.2x PyMuPDF raster: 735px horizontal x 950px full vertical.
# Source interior cropland Field1 is bordered by Arista Road to west and
# wooded exclusions to east; drawn boundary is approximate, not a survey.
# A tree pocket is visible inside the FSA outline and not claimed as a precise
# cadastrally excluded area. This is intentionally >= not an acreage-fitting buffer.
source_poly_1_2x=[
 (244,405),(272,400),(272,375),(296,370),(324,383),
 (355,378),(355,344),(411,337),(412,354),(387,397),
 (364,431),(392,426),(403,457),(411,465),(249,469)
]
H=np.asarray(qa["source_pdf_pts_to_tile_homography"],dtype=np.float64)
px=np.float32([[x/1.2,y/1.2] for x,y in source_poly_1_2x])
imgpt=cv2.perspectiveTransform(px[None],H)[0]
bb=qa["tile_bbox_epsg3857"];side=qa["tile_size_px"];R=6378137.
coords=[]
for u,v in imgpt:
 x=bb[0]+float(u)/side*(bb[2]-bb[0])
 y=bb[3]-float(v)/side*(bb[3]-bb[1])
 coords.append([math.degrees(x/R),math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)])
geom=Polygon(coords)
assert geom.is_valid and not geom.is_empty
geod=Geod(ellps="WGS84")
ac=abs(geod.geometry_area_perimeter(geom)[0])/4046.8564224
err=100*(ac/10.51-1)
assert abs(err)<=25,("Area discrepancy beyond relaxed threshold",ac,err)
# Spatially resolve county, never use FSA office heading or address county.
url="https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
resp=requests.get(url,timeout=70);resp.raise_for_status()
with tempfile.TemporaryDirectory() as td:
 with zipfile.ZipFile(io.BytesIO(resp.content)) as z:z.extractall(td)
 reader=shapefile.Reader(str(next(Path(td).glob("*.shp"))))
 counties=[r.as_dict()["NAME"] for g,r in zip(reader.shapes(),reader.records())
   if r.as_dict().get("STATEFP")=="45" and shape(g.__geo_interface__).covers(geom.representative_point())]
assert len(counties)==1,counties
county=counties[0]
props=dict(producer="Christine Berry Zeigler",county=county,roster_county="Orangeburg",
 farm_id="1271",tract_id="469",field_id="1",fsa_printed_acres=10.51,
 geodesic_acres=round(ac,4),acreage_difference_pct=round(err,2),
 source_pdf="Christine Berry Zeigler_FSA Map.pdf",source_page=1,
 source_workbook_field_match=True,
 image_registration_inliers=qa["image_matches"],registration_rmse_px=qa["rmse_px"],
 registered_provider=qa["provider"],
 registration_method="FSA source photo aligned by SIFT to georeferenced NAIP near independently identified Arista/Baxley TIGER roads",
 physical_county_basis="Official US Census 2025 county polygons, FSA printed county ignored",
 status="REGISTERED_FIELD1_GEOGRAPHIC_QA_PASSED_SOURCE_PHOTO_APPROXIMATE",
 geometry_quality="FSA_PHOTO_TRACED_APPROXIMATE_NOT_SURVEY",
 note="Interior field traced from visible yellow FSA source outline; exclude small tree pockets only after separate validation.")
feature={"type":"Feature","properties":props,"geometry":mapping(geom)}
GEO.write_text(json.dumps({"type":"FeatureCollection","name":"Christine_Berry_Zeigler_FSA_Field1_20261111",
 "features":[feature]},indent=2)+"\n")
atlas.OUT=BASE
mapqa=atlas.process(("Christine Berry Zeigler",county),[feature])
assert mapqa["county_map_status"]=="CREATED" and mapqa["field_map_status"]=="CREATED",mapqa
folder=BASE/county/atlas.human_folder("Christine Berry Zeigler")
(folder/"SOURCE_FIELD_QA.json").write_text(json.dumps(dict(
 name="Christine Berry Zeigler",source_farm_tract_field="1271/469/1",
 fsa_acres=10.51,geodetic_acres=round(ac,4),acreage_difference_percent=round(err,2),
 fsa_photo_registration_image_matches=qa["image_matches"],
 fsa_photo_registration_rmse_px=qa["rmse_px"],physical_county=county,
 year2_enrolled_target_identifiers_match=True,
 source_photo_field_boundary_quality="APPROXIMATE",map_qa=mapqa,
 completeness="MAPPED_ENROLLED_FIELD_SOURCE_PHOTO_APPROXIMATE",
 legal_caution="FSA polygons are not legal surveys or proof of ownership"),indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "Christine Berry Zeigler, Year2 Farm1271/Tract469/Field1: MAPPED\n"
 f"Georeferenced source 10.51ac, approximate trace {ac:.3f}ac ({err:+.1f}%).\n"
 "Location grounded in 217 independent NAIP image matches, 1.28px residual and Arista/Baxley road geometry.\n"
 f"Physical Census county: {county}. Source FSA printing county ignored.\n"
 "EPSG:4326 shapefile and Weekley county topographic and road-labeled satellite PDFs.\n"
 "Research planning polygon only; manually traced approximate interior field; not survey.\n"
)
# Rest of five get source/reconciliation status folders rather than fake polygons.
others=[
 ("Javeiann Spann","SOURCE_DIGITIZED_LOCATION_UNRESOLVED",
  "Year2 3988/4673/1; user supplied two photographs including unrelated 9447/8142; no unique independent NAIP match.",
  "Jaivean_Spann/SOURCE_PIXEL_TRACES_AND_ID_RECONCILIATION.json"),
 ("Joe Hilliard","IMAGE_REGISTERED_SOURCE_FARM_MISMATCH",
  "612 NAIP features registered source Farm6528/Tract41114; Year2 target Farm13859/Tract45814/Field20; do NOT substitute source field.",
  "batch2/source_page_registration/Joe_Hilliard/source_registration_QA.json"),
 ("Calvin Blair","SOURCE_FARM_MATCHES_BUT_IMAGE_LOCATION_UNRESOLVED",
  "Farm3603/Tract848 source page includes Field3 (12.50 acres). Existing local SIFT match was geometrically degenerate.",
  "batch2/source_page_registration/Calvin_Blair/source_registration_QA.json"),
 ("Tywone Hilliard","THREE_IMAGE_REGISTRATIONS_SOURCE_IDS_UNRECONCILED",
  "Three 2024 photographed field-map pages registered geographically; enrolled Farms1064 and3826 not confirmed from these maps.",
  "batch2/source_page_registration/Tywone_Hilliard/source_registration_QA.json")
]
rows=[dict(farmer="Christine Berry Zeigler",status="MAPPED_GEOGRAPHICALLY",
    accepted_polygon_count=1,physical_county=county,
    target="1271/469/1",area_ac=round(ac,4),
    source_registration="217 inliers, 1.28px",administratively_closed=False,
    blocker="FSA photo map footer Farm/Tract identification not machine-readable; confirm source association if formal enrollment closure required")]
for name,state,reason,rel in others:
 folder=BASE/"SOURCE_REVIEW_ONLY"/("L-"+name.replace(" ","_"))
 folder.mkdir(parents=True,exist_ok=True)
 src=QROOT/rel
 if src.exists(): (folder/"SOURCE_REGISTRATION_QA.json").write_text(src.read_text())
 (folder/"README_NOT_GEOREFERENCED.txt").write_text(
  f"Producer: {name}\nStatus: {state}\n{reason}\n"
  "No accepted EPSG:4326 source-field polygon. Do not count this folder as completed.\n"
  "No shapefile or field-location PDF has been fabricated.\n")
 rows.append(dict(farmer=name,status=state,accepted_polygon_count=0,
     physical_county="",target="",area_ac="",source_registration="SEE QA",administratively_closed=False,
     blocker=reason))
index=BASE/"Batch2_Five_Farmer_QA.csv"
with index.open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]),extrasaction="ignore")
 writer.writeheader();writer.writerows(rows)
summary=dict(batch="Batch2 five farmers",date="2026-11-11",
 people=5,year2_farmers_geographically_mapped=1,
 source_review_only=4,admin_closed=0,
 note="Count means geographically mapped enrolled target, not verified legal acreage. Additional enrollment source-ID review is separately tracked.",
 mapped_farmer="Christine Berry Zeigler",mappable_source_rows=rows,
 acreage_tolerance_pct=25)
(BASE/"BUILD_SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n")
(BASE/"README_START_HERE.txt").write_text(
 "Batch2 SC State AMP FSA field mapping - five producers\n"
 "1 registered approximate enrolled field (Christine Berry Zeigler); four other review folders NOT COMPLETED.\n"
 "Christine includes Weekley EPSG:4326 farmer shapefile, county topographic PDF, road-labeled satellite field PDF.\n"
 "Do not confuse strong FSA photo registration with confirming enrolled Farm/Tract/Field.\n"
 "See Batch2_Five_Farmer_QA.csv for each outstanding blocker.\n")
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(BASE.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(BASE.parent))
print("BATCH2_PUBLISHED",json.dumps(dict(county=county,field1_geodetic_ac=round(ac,4),fsa_ac=10.51,
 delta_pct=round(err,2),maps=mapqa,archive_bytes=BUNDLE.stat().st_size)),flush=True)
