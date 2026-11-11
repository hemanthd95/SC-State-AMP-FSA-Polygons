#!/usr/bin/env python3
"""One Weekley-format folder per farmer: merge Antron Cinnabar+Gordon
provisional FSA source fields, preserve two distinct satellite close-up pages.
Strictly retains provisional source-identification and positional QA flags.
"""
import io,json,zipfile,csv
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/antron_williams_combined_20261111"
ZIP=ROOT/"deliverables/Antron_Williams_Combined_Provisional_Weekley_Folder_20261111.zip"
OUT.mkdir(parents=True,exist_ok=True)
geo_sources=[
ROOT/"geojson/counties/antron_williams_gordon_manual_road_registration_20261111.geojson",
ROOT/"geojson/counties/antron_williams_cinnabar_provisional_road_control_20261111.geojson",
]
geo=[]
for path in geo_sources:
 doc=json.loads(path.read_text())
 for f in doc["features"]:
  assert f["properties"]["producer"]=="Antron Williams"
  assert f["properties"]["farm_id"]=="11990"
  assert f["properties"]["tract_id"]=="44081"
  geo.append(f)
ids=[f["properties"]["field_id"] for f in geo]
assert len(set(ids))==len(ids)==6,ids
import publish_per_farmer_weekley_style_20261110 as pub
pub.OUT=OUT
qa=pub.process(("Antron Williams","Orangeburg"),geo)
assert qa["county_map_status"]=="CREATED" and qa["field_map_status"]=="CREATED"
folder=OUT/"Orangeburg"/"L-Williams, Antron"
assert folder.is_dir()
# Replace the unreadably wide single satellite field map with two original
# close-up PDFs from independently generated road sub-area packages.
farmer_name="AntronWilliams"
target=folder/(farmer_name+"-FieldMap.pdf")
target.unlink(missing_ok=True)
sources=[
ROOT/"deliverables/Antron_Williams_Cinnabar_Road_Provisional_GIS_20261111.zip",
ROOT/"deliverables/Antron_Williams_Gordon_Drive_Provisional_GIS_20261111.zip"]
merged=fitz.open()
for area,archive in zip(["Cinnabar Road","Gordon Drive"],sources):
 with zipfile.ZipFile(archive) as z:
  matches=[n for n in z.namelist() if n.endswith(farmer_name+"-FieldMap.pdf")]
  if len(matches)!=1:raise ValueError((archive,matches))
  doc=fitz.open(stream=z.read(matches[0]),filetype="pdf")
  assert len(doc)==1,(archive,len(doc))
  merged.insert_pdf(doc)
  doc.close()
merged.save(target,garbage=4,deflate=True)
merged.close()
with fitz.open(target) as verify:
 assert len(verify)==2, "Expected two separately zoomed satellite pages"
 for i,page in enumerate(verify):
  pix=page.get_pixmap(matrix=fitz.Matrix(1.1,1.1),colorspace=fitz.csRGB,alpha=False)
  out=folder/f"Area_{i+1}_FieldMap_Preview.jpg"
  pix.save(str(out),jpg_quality=83)
doc={"type":"FeatureCollection",
 "name":"Antron_Williams_Farm11990_Tract44081_Provisional_Combined_20261111",
 "features":geo}
(folder/"REGISTERED_FIELDS.geojson").write_text(json.dumps(doc,indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "ANTRON WILLIAMS - FARM 11990 TRACT 44081\n"
 "STATUS: PROVISIONALLY GEOREFERENCED SOURCE FIELDS; NOT YET COMPLETE AGAINST ENROLLMENT.\n"
 "Data layers: Cinnabar FSA page5 Fields7,18,20; Gordon FSA page7 Fields61,3,16.\n"
 "Field19 was REJECTED (computed acreage differs from FSA by 96%).\n"
 "The Year2 master says enrolled Fields6 and7; source Field61 NOT proven to mean Field6.\n"
 "Two registration methods: Cinnabar = 13 TIGER road controls, 3.38m road-curve RMSE,\n"
 "  but no successful independent NAIP image-feature match.\n"
 "Gordon = three manual road-control points against georeferenced NAIP, provisional.\n"
 "These are approximate FSA research field polygons, NOT surveys or ownership evidence.\n"
 "Each field's source registration limitations are retained in GeoJSON properties.\n"
 "One EPSG:4326 producer shapefile in AntronWilliams.shp folder.\n"
 "CountyMap.pdf one topo overview; FieldMap.pdf two satellite close-up pages.\n"
 "Tax/producer-identification pages are excluded from this package.\n")
qa["field_map_pages"]=2
qa["source_field_ids"]=ids
qa["farmer_enrollment_complete"]=False
qa["unverified_enrollment_field"]="6"
qa["excluded_source_field"]="19"
qa["position_confidence"]="PROVISIONAL_ALL_FIELDS"
qa["registration_limitations"]=[
 "Cinnabar source road fit not independently SIFT validated",
 "Gordon source manual controls require independent check",
 "Field61 not matched to enrolled Field6"]
(folder/"FINAL_QA.json").write_text(json.dumps(qa,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "SC State AMP - one farmer Weekley-format bundle\n"
 "Antron Williams six PROVISIONALLY georeferenced source fields, not a closed enrollment.\n"
 "Open Orangeburg/L-Williams, Antron/README_STATUS_FIRST.txt first.\n"
 "Do not equate 'a registered source field' with 'a fully completed farmer'.\n")
ZIP.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ZIP,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("FINAL_ANTRON",json.dumps(dict(features=len(geo),fields=ids,field_pages=2,
 archive_bytes=ZIP.stat().st_size,two_road_names_pass=qa["two_road_names_pass"],
 closed_enrollment=False)),flush=True)
