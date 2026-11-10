#!/usr/bin/env python3
"""Package all seven farmer research records, preserving 'not yet georeferenced'
statuses while using the Weekley-format maps/shapefiles for verified features.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,csv,zipfile,io,math
import fitz
import requests
from PIL import Image,ImageDraw,ImageFont
import publish_per_farmer_weekley_style_20261110 as pub

ROOT=Path(__file__).resolve().parents[1]
SRCROOT=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT=ROOT/"deliverables/recovery_seven_weekley_20261110"
ZIP=ROOT/"deliverables/SC_AMP_Seven_Farmer_Recovery_20261110.zip"
OUT.mkdir(parents=True,exist_ok=True)
pub.OUT=OUT
TARGS={x["name"]:x for x in json.loads((ROOT/"analysis/recovery7_20261110/address_first_anchors.json").read_text())}
FRACTION={
 "Angale Johnson":(2,3,"Two source-registered fields, Farm22564 Tract17265 Field13 and Tract17268 Field2; Farm22560 Tract17266 Field1 remains unregistered. Both registered field traces have lower-inlier QA flags."),
 "Annette Weekley":(0,1,"Source photo is strongly georegistered but the enrolled Field2 is absent; two independently georegistered CONTEXT fields 3 and 10 must not be represented as enrollment Field2."),
 "Albert Vareen":(0,1,"Requested source Field1 is visually identified, but wide-area aerial registration has not confirmed the property. Do not treat a geocoded residence or PDF pixel polygon as a georeferenced field."),
 "Rick Boswell":(1,1,"Previously registered York Farm4330 Tract8916 Field1 retained from existing curated GeoJSON."),
 "Christopher Riley":(0,1,"The source page for Farm7832 Tract5341 shows Fields 1,4,5 but not requested Field2. Field2 appears in source Tract5340, a different tract; do not substitute."),
 "Tyrease Riley":(0,1,"Farm3603 Tract848 Field1 visible in source; a robust NAIP/Esri geographic image match remains unconfirmed."),
 "Francena Ellis":(2,2,"Farm4083 Tract10683 Fields3 and7 registered against geocoded Browning Gate Road near Estill; true geographic county Hampton, not original Jasper workbook roster.")
}
NAMES=list(FRACTION)
GEO=ROOT/"geojson/counties/recovery7_address_registered_20261110.geojson"
OLD=ROOT/"geojson/counties/york_registered_selected_field.geojson"
all_features=json.loads(GEO.read_text())["features"]
all_features+=json.loads(OLD.read_text())["features"]
groups={}
for f in all_features:
 p=f["properties"];n=p.get("producer")
 if n not in NAMES:continue
 county=p.get("county")
 groups.setdefault((n,county),[]).append(f)
# No unregistered field polygon is introduced in this bundle.
rows=[]
def map_one(key,ff):
 qa=pub.process(key,ff)
 name,county=key
 selected,requested,note=FRACTION[name]
 qa.update(workbook_selected_fields_mapped=selected,workbook_selected_fields_requested=requested,
    batch_status="ALL_TARGET_FIELDS_GEOGRAPHICALLY_REGISTERED" if selected==requested else
       "PARTIALLY_REGISTERED_OR_SOURCE_ONLY",
    notes=note)
 return qa
with ThreadPoolExecutor(max_workers=4) as executor:
 futs={executor.submit(map_one,k,features):k for k,features in groups.items()}
 for fut in as_completed(futs):
  k=futs[fut]
  try:rows.append(fut.result())
  except Exception as exc:
   rows.append(dict(producer=k[0],physical_county=k[1],batch_status="BUILD_ERROR",error=str(exc)))
# Preserve unregistered participants in same deliverable, without false shapefiles.
def pending_folder(name):
 t=TARGS[name]
 roster=t["roster_county"]
 dest=OUT/"UNREGISTERED__SOURCE_ONLY"/(pub.human_folder(name))
 dest.mkdir(parents=True,exist_ok=True)
 doc=fitz.open(SRCROOT/t["source_pdf"])
 good_pages=t["pages"]
 if name=="Christopher Riley":good_pages=[2,3]
 subset=fitz.open()
 for pg in good_pages:subset.insert_pdf(doc,from_page=pg-1,to_page=pg-1)
 subset.save(dest/"FSA_Source_Pages_UNREGISTERED.pdf",garbage=4,deflate=True)
 subset.close();doc.close()
 (dest/"README_GEOGRAPHIC_REGISTRATION_PENDING.txt").write_text(
  f"SCSU AMP: {name}\n"
  f"Excel roster county: {roster}\n"
  f"Excel address: {t['address']}\n"
  f"Requested FSA identifiers: {t['fields']}\n"
  f"Source: {t['source_pdf']}, pages {good_pages}\n"
  f"CURRENT STATUS: NO ACCEPTED FIELD GEOMETRY. NO SHAPEFILE GENERATED.\n"
  f"Why: {FRACTION[name][2]}\n"
  "The source PDF pages are NOT georeferenced; do NOT import them as field boundaries.\n"
  "The county printed in an FSA office PDF is ignored for physical-field decisions.\n")
 row=dict(producer=name,physical_county="UNVERIFIED",folder=str(dest.relative_to(OUT)),
    workbook_selected_fields_mapped=0,workbook_selected_fields_requested=FRACTION[name][1],
    batch_status="NO_GEOREFERENCED_SELECTED_FIELD",notes=FRACTION[name][2],
    county_map_status="NOT_REPRESENTABLE_AS_FIELD",field_map_status="SOURCE_PDF_ONLY",two_road_names_pass=False)
 rows.append(row)
for name in NAMES:
 if not any(r.get("producer")==name for r in rows):pending_folder(name)
# Annette and Angale have partial source matches: add QA notes in their map folders.
for r in rows:
 name=r.get("producer")
 if name in FRACTION and r.get("batch_status")=="PARTIALLY_REGISTERED_OR_SOURCE_ONLY":
  folder=OUT/r["folder"]
  (folder/"IMPORTANT_WORKBOOK_SELECTION_QA.txt").write_text(FRACTION[name][2]+"\n")
rows.sort(key=lambda r:r.get("producer",""))
headers=sorted(set().union(*(set(x) for x in rows)))
with (OUT/"Seven_Farmer_Recovery_Index_QA.csv").open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=headers,extrasaction="ignore");w.writeheader();w.writerows(rows)
selected_mapped=sum(int(r.get("workbook_selected_fields_mapped") or 0) for r in rows)
selected_req=sum(int(r.get("workbook_selected_fields_requested") or 0) for r in rows)
overview={"date":"2026-11-10","farmers":7,"registered_farmers":len(groups),
 "workbook_selected_field_count":selected_req,"workbook_selected_fields_georegistered":selected_mapped,
 "all_georeferenced_features_included":sum(len(v) for v in groups.values()),
 "status":{"SOURCE_MAP_NOT_SAME_AS_WORKBOOK_FIELD": ["Annette Weekley","Christopher Riley"],
    "UNLOCATED_AFTER_NAIP_SEARCH":["Albert Vareen","Christopher Riley","Tyrease Riley"],
    "PARTIAL_LOW_INLIER":["Angale Johnson"],
    "SOURCE_FIELD_IDS_MATCH": ["Rick Boswell","Francena Ellis"]},
 "county_rule":"Use Excel addresses to locate field search; FSA office county is not an indicator of real location",
 "critical_note":"Four farmer map folders contain geographically registered source polygons. Three remaining farmer folders explicitly carry UNREGISTERED source pages only, NOT shapefiles. One mapped farmer (Annette) has only non-enrolled source fields. Do not claim all seven selected farms complete."
}
(OUT/"BUILD_SUMMARY.json").write_text(json.dumps(overview,indent=2))
(OUT/"README_START_HERE.txt").write_text(
 "SC State AMP - seven farmer recovery package, 10 Nov 2026\n"
 "Uses the William Weekley reference format for REGISTERED polygons:\n"
 "individual farmer shapefiles EPSG:4326, CountyMap topography, FieldMap aerial with two road names.\n"
 "All source boundaries are approximate FSA photo traces, not legal surveys.\n\n"
 "DO NOT CONFUSE SOURCE-ONLY FOLDERS WITH COMPLETED GEOREFERENCING.\n"
 "The three unresolved records are under UNREGISTERED__SOURCE_ONLY and have no shapefile.\n"
 "Annette Weekley has fields 3 and 10 mapped for context, but not the workbook's Field2.\n"
 "Angale Johnson Field1 remains unregistered; Fields2 and13 have lower-inlier QA flags.\n"
 "Original workbook county, FSA office county and field's physical county are distinct attributes.\n"
 "See Seven_Farmer_Recovery_Index_QA.csv and BUILD_SUMMARY.json for exact status.\n")
ZIP.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ZIP,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("SUMMARY",json.dumps(overview),flush=True)
print("ZIP",ZIP,ZIP.stat().st_size,flush=True)
