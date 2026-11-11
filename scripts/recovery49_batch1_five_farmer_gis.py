#!/usr/bin/env python3
"""Batch 1 of five outstanding AMP farmers (2026-11-11).
Build source-identified, NAIP-registered FSA research polygons where robust
homographies and areas pass. Never silently call unresolved farmers complete.
Preserves previous Jasper and Margaret GIS from previously published ZIPs.

Outputs:
- source-verified WGS84 GeoJSON for Charles/Joseph/Arthur
- one Weekley-style shapefile and county/field PDF pair for each newly mapped farmer
- existing Jasper/Margaret Weekley folders, unchanged
- QA register for each, batch ZIP, individual ZIPs for new mappings
"""
from pathlib import Path
import io,json,math,csv,zipfile,tempfile,shutil
import requests,cv2,numpy as np,shapefile
from shapely.geometry import Polygon,shape,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as atlas

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/batch1_five_farmer_recovery_20261111"
BUNDLE=ROOT/"deliverables/AMP_Batch1_Five_Farmer_GIS_20261111.zip"
GEO=ROOT/"geojson/counties/recovery49_batch1_source_registered_20261111.geojson"
QA=OUT/"Batch1_Farmer_QA.csv"
OUT.mkdir(parents=True,exist_ok=True);GEO.parent.mkdir(parents=True,exist_ok=True)
REG_ROOT=ROOT/"analysis/recovery49_20261111"
GEOD=Geod(ellps="WGS84")
R=6378137.
# SOURCE REFERENCE: source PDF page 1 rendered to 980 x 1268px. All outlines
# follow visible FSA labels, not field guesses from addresses.
# The selected traces are only a SUBSET of the shown fields; mismatched or
# absent fields remain explicitly blocked in README/QA. Not cadastral surveys.
SPECS=[
 dict(name="Charles Bright Jr.",src="wave4/Charles_Bright_Jr_",
      pdf="Bright, Charles, JR_ FSAmap.pdf",farm="2715",tract="3022",
      expected="No selected Field ID in Year2 master; source page1 also Fields 9,10,3; page2 is Tract3021",
      qa_mode="SOURCE_PARTIAL_NOT_YEAR2_COMPLETE",
      shapes=[dict(field="2",acres=5.23,pts=[(397,507),(550,496),(609,681),(481,731)])]),
 dict(name="Joseph Gadson",src="wave4/Joseph_Gadson",
      pdf="Joseph Gadson_FSAmap.pdf",farm="4547",tract="4482",
      expected="Year2 enrollment Farm/Tract/Field missing; source fields 12,3,10,9,4 visible",
      qa_mode="SOURCE_PARTIAL_ENROLLMENT_IDS_MISSING",
      shapes=[dict(field="3",acres=1.88,pts=[(502,366),(651,416),(627,458),(610,471),(547,460),(509,447),(486,437),(475,410),(478,386)]),
              dict(field="4",acres=.60,pts=[(517,612),(544,607),(570,614),(580,632),(570,651),(547,669),(521,663),(500,637)])]),
 dict(name="Arthur Cobbs",src="wave3/Arthur_Cobbs",
      pdf="Arthur Cobbs_FSA Map.pdf",farm="548",tract="295",
      expected="Year2 Farm548, source Farm548/Tract295 Field1; only labeled cropped field on source map",
      qa_mode="YEAR2_FARM_AND_SINGLE_SOURCE_FIELD_MATCH",
      shapes=[dict(field="1",acres=1.80,pts=[(433,258),(566,263),(555,330),(457,327),(429,299)])]),
]
# Full 46-county official Census index; original SC repository county layer is incomplete.
COUNTIES=[]
def census_counties():
 global COUNTIES
 if COUNTIES:return COUNTIES
 url="https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
 response=requests.get(url,timeout=55);response.raise_for_status()
 with tempfile.TemporaryDirectory() as tmp:
  with zipfile.ZipFile(io.BytesIO(response.content)) as z:z.extractall(tmp)
  reader=shapefile.Reader(str(next(Path(tmp).glob("*.shp"))))
  COUNTIES=[(r.as_dict()["NAME"],shape(s.__geo_interface__)) for s,r in zip(reader.shapes(),reader.records())
            if r.as_dict().get("STATEFP")=="45"]
 assert len(COUNTIES)==46,len(COUNTIES)
 return COUNTIES
def physical_county(g):
 p=g.representative_point()
 result=[name for name,geom in census_counties() if geom.covers(p)]
 if len(result)!=1:raise RuntimeError("Physical county not uniquely determined: "+repr(result))
 return result[0]
def to_polygon(raw,q):
 H=np.array(q["source_pdf_page_points_to_tile_H"],dtype=float)
 bbox=q["tile_bbox_epsg3857"];S=q["tile_size_px"]
 pts=np.float32([[(x/980.)*612.,(y/1268.)*792.] for x,y in raw])
 mapped=cv2.perspectiveTransform(pts[None],H)[0]
 coords=[]
 for u,v in mapped:
  mx=bbox[0]+float(u)/S*(bbox[2]-bbox[0])
  my=bbox[3]-float(v)/S*(bbox[3]-bbox[1])
  coords.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
 polygon=Polygon(coords)
 if not polygon.is_valid or polygon.is_empty:raise RuntimeError("FSA trace creates invalid polygon")
 return polygon
records=[];new_features=[]
atlas.OUT=OUT
for spec in SPECS:
 path=REG_ROOT/spec["src"]/"registration_qa.json"
 q=json.loads(path.read_text())
 assert q["valid_geometric_match"] and q["imagery_provider"]=="USGS_NAIP"
 minimum=35 if spec["name"]=="Arthur Cobbs" else 200
 assert q["inliers"]>=minimum and q["rmse_px"]<.8,(spec["name"],q["inliers"],q["rmse_px"])
 current=[]
 for entry in spec["shapes"]:
  geom=to_polygon(entry["pts"],q)
  area=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
  difference=100*(area/entry["acres"]-1)
  assert abs(difference)<9,(spec["name"],entry["field"],area,difference)
  county=physical_county(geom)
  props=dict(producer=spec["name"],county=county,
    farm_id=spec["farm"],tract_id=spec["tract"],field_id=entry["field"],
    source_pdf=spec["pdf"],source_page=1,
    source_fsa_acres=entry["acres"],geodesic_area_acres=round(area,4),
    acreage_difference_pct=round(difference,2),
    source_workbook_field_match=(spec["name"]=="Arthur Cobbs"),
    image_registration_inliers=q["inliers"],
    registration_rmse_pixels=q["rmse_px"],
    registration_provider=q["imagery_provider"],
    registration_method="SIFT feature matching FSA raster page 1 to independently georeferenced USGS NAIP",
    geometry_quality="SOURCE_FIELD_PHOTO_TRACE_APPROXIMATE_NOT_SURVEY",
    farminer_completion_status=spec["qa_mode"],
    attribution_warning="Source field boundary only; not a land survey or verified ownership")
  current.append(dict(type="Feature",properties=props,geometry=mapping(geom)))
  records.append(dict(farmer=spec["name"],physical_county=county,
    farm_id=spec["farm"],tract_id=spec["tract"],field_id=entry["field"],
    fsa_acres=entry["acres"],mapped_acres=round(area,4),
    area_delta_pct=round(difference,2),image_matches=q["inliers"],
    image_rmse_px=q["rmse_px"],status="REGISTERED_SOURCE_FIELD_APPROXIMATE",
    farmer_closed=(spec["name"]=="Arthur Cobbs"),notes=spec["expected"]))
 assert len(set(f["properties"]["county"] for f in current))==1
 county=current[0]["properties"]["county"]
 print("FARMER_IMAGE_TRACE",spec["name"],county,[(f["properties"]["field_id"],
  f["properties"]["geodesic_area_acres"]) for f in current],flush=True)
 new_features+=current
 qa=atlas.process((spec["name"],county),current)
 assert qa["field_map_status"]=="CREATED" and qa["county_map_status"]=="CREATED"
 assert qa["two_road_names_pass"],(spec["name"],qa)
 folder=OUT/county/atlas.human_folder(spec["name"])
 (folder/"FIELD_QA_BATCH1.json").write_text(json.dumps(dict(
   farmer=spec["name"],farmer_completion_state=spec["qa_mode"],
   source_pdf=spec["pdf"],source_page=1,source_record=spec["expected"],
   source_only_field_ids=[f["properties"]["field_id"] for f in current],
   not_digitized_source_fields=("9,10,3 (Tract3022) and page2 Tract3021" if "Bright" in spec["name"] else
     "12,10,9" if "Joseph" in spec["name"] else "none"),
   geometry_quality="FSA-photo research approximation, not legal survey",
   registration_inliers=q["inliers"],registration_rmse_px=q["rmse_px"],
   individual_features=[f["properties"] for f in current],cartography=qa),indent=2)+"\n")
 (folder/"README_COMPLETION_STATUS.txt").write_text(
   f"SCSU AMP / {spec['name']}\n"
   f"Source Farm {spec['farm']}, Tract {spec['tract']}. Fields included: "
     +", ".join(f["properties"]["field_id"] for f in current)+"\n"
   f"STATUS: {spec['qa_mode']}\n"
   f"ENROLLMENT STATUS: {spec['expected']}\n"
   "Only the source-labeled, georeferenced, acreage-checked field geometries were included.\n"
   "Do not mistake this subset for a completed enrolled farmer when selection is missing.\n"
   "WGS84 (EPSG:4326) farmer shapefile, topographic context and road-labeled satellite PDFs.\n"
   "FSA administrative/printing county was ignored when determining physical location.\n"
   "Geometries are approximate photo-source field outlines, NOT legal/cadastral surveys.\n")
 individual=ROOT/"deliverables"/(spec["name"].replace(" ","_").replace(".","")+"_Batch1_GIS_20261111.zip")
 with zipfile.ZipFile(individual,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
  for p in folder.rglob("*"):
   if p.is_file():z.write(p,p.relative_to(OUT))
 print("FARMER_ZIP",individual.name,individual.stat().st_size,flush=True)
GEO.write_text(json.dumps({"type":"FeatureCollection",
 "name":"SC_AMP_Batch1_Charles_Joseph_Arthur_NAIP_Accepted_Partial",
 "features":new_features},indent=2)+"\n")
# Carry forward the two previously accepted packages as-is; avoid rewriting their polygons.
for name,archive in [
 ("Jasper Summers",ROOT/"deliverables/Jasper_Summers_Expanded_Three_Field_GIS_20261111.zip"),
 ("Margaret Berry",ROOT/"deliverables/Margaret_Berry_Updated_Two_Farm_Weekley_GIS_20261111.zip")]:
 with zipfile.ZipFile(archive) as z:
  paths=[p for p in z.namelist() if p.endswith("REGISTERED_FIELDS.geojson")]
  assert len(paths)==1,(name,paths)
  source=json.loads(z.read(paths[0]))
  features=source["features"]
  county=features[0]["properties"].get("county","Orangeburg")
  assert all(f["properties"].get("county")==county for f in features)
  dest=OUT/county/atlas.human_folder(name)
  # ZIP contains one already mapped farmer, not private source documents.
  folder_from_zip="/".join(paths[0].split("/")[:-1])+"/"
  for item in z.infolist():
   if item.is_dir() or not item.filename.startswith(folder_from_zip):continue
   rel=Path(item.filename[len(folder_from_zip):])
   if not rel.parts:continue
   (dest/rel).parent.mkdir(parents=True,exist_ok=True)
   (dest/rel).write_bytes(z.read(item))
  if name=="Jasper Summers":
   status="PARTIAL_NOT_CLOSED"
   note="Farm13709 Fields8/17 mapped; enrollment field blank and Tract45512 Fields16/27 remain unregistered"
  else:
   status="PARTIAL_NOT_CLOSED"
   note="Farm10939 Field3 mapped; older Farm11782 Field13 area differs substantially from 7.53 FSA acres"
  (dest/"BATCH1_STATUS_README.txt").write_text(
    f"{name} - retained existing registered polygons without altering geometry.\n"
    f"STATUS: {status}\n{note}\n"
    "Do not count as fully completed based on presence of shapefile alone.\n")
  records.append(dict(farmer=name,physical_county=county,
    farm_id="13709;13653" if name=="Jasper Summers" else "10939;11782",
    tract_id="",field_id="",fsa_acres="",mapped_acres="",
    area_delta_pct="",image_matches="",image_rmse_px="",
    status=status,farmer_closed=False,notes=note))
  print("CARRIED_FORWARD_UNMODIFIED",name,len(features),flush=True)
assert len(set(r["farmer"] for r in records))==5
fields=["farmer","physical_county","farm_id","tract_id","field_id","fsa_acres",
        "mapped_acres","area_delta_pct","image_matches","image_rmse_px",
        "status","farmer_closed","notes"]
with QA.open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
 writer.writeheader();writer.writerows(records)
summary={
 "project":"SC State AMP FSA Farm GIS recovery - Batch1 (five farmers)",
 "date":"2026-11-11",
 "participants":["Charles Bright Jr.","Joseph Gadson","Arthur Cobbs","Jasper Summers","Margaret Berry"],
 "newly_accepted_source_geometries":len(new_features),
 "newly_closed_year2_farmers":["Arthur Cobbs"],
 "not_closed":["Charles Bright Jr.","Joseph Gadson","Jasper Summers","Margaret Berry"],
 "counting_rule":"Only Arthur Cobbs meets the enrolled farm+single mapped source field test; all others are partial or enrollment identifiers missing.",
 "provenance":"Independently NAIP-registered images, visual FSA outline and acreage gate for new source polygons; Jasper and Margaret copied from existing GIS ZIPs.",
 "survey_disclaimer":"All FSA photo-based outlines are approximate research planning boundaries, not cadastral surveys."
}
(OUT/"BATCH1_BUILD_SUMMARY.json").write_text(json.dumps(summary,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "SC STATE AMP - BATCH 1 OF 5 FARMERS\n"
 "New georeferenced source-field GIS for Arthur Cobbs, Charles Bright Jr., Joseph Gadson.\n"
 "Existing separate per-farmer mapped GIS for Jasper Summers and Margaret Berry carried forward unchanged.\n"
 "Year2 status: Arthur Cobbs complete against known Farm548/Tract295/Field1; four remain QA open.\n"
 "Some FSA source fields are NOT INCLUDED because not yet digitized/area verified.\n"
 "Use Batch1_Farmer_QA.csv and each farmer's status README. Photo-source boundaries are not surveys.\n")
BUNDLE.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("FINAL_BATCH1",json.dumps(dict(summary=summary,
  zip_bytes=BUNDLE.stat().st_size,root=str(OUT))),flush=True)
