#!/usr/bin/env python3
"""Finalize Batch2 evidence after wider Calvin (369 tiles, degenerate) search.
Preserve all three previously mapped producer folders and one completed Year2
farmer. Add independently verified Calvin/Tyrease pixel-identical shared farm
crosswalk so the map need only be registered once in future.
"""
import json,csv,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/recovery49_batch2_five_20261111"
BUNDLE=ROOT/"deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip"
with zipfile.ZipFile(BUNDLE) as z:
 for item in z.infolist():
  if item.is_dir():continue
  f=ROOT/"deliverables"/item.filename
  f.parent.mkdir(parents=True,exist_ok=True)
  f.write_bytes(z.read(item))
q=json.loads((ROOT/"analysis/recovery49_20261111/batch2/calvin_wide_match/calvin_wide_search_QA.json").read_text())
assert q["status"]=="WEAK_OR_DEGENERATE_NOT_ACCEPTED" and q["imagery_tiles_loaded"]>=300
cross=json.loads((ROOT/"analysis/recovery49_20261111/batch2/calvin_tyrease_shared_source_QA.json").read_text())
assert cross["same_source_page_pixels"] and cross["farm_id"]=="3603"
folder=OUT/"SOURCE_REVIEW_ONLY"/"L-Calvin_Blair"
assert folder.exists()
(folder/"WIDE_AERIAL_SEARCH_QA.json").write_text(json.dumps(q,indent=2)+"\n")
(folder/"CALVIN_TYREASE_SHARED_FSA_SOURCE_QA.json").write_text(json.dumps(cross,indent=2)+"\n")
(folder/"README_NOT_GEOREFERENCED.txt").write_text(
 "Calvin Blair Farm3603/Tract848/Field3 (12.50 FSA acres): not yet located geographically.\n"
 "A widened search loaded 369 USGS NAIP and Esri aerial tiles within roughly 11km of the Excel address.\n"
 "Best SIFT feature match was degenerate (target spatial spread zero), so no geographic polygon was accepted.\n"
 "Calvin Blair and Tyrease Riley supplied pixel-identical FSA map pages for Farm3603/Tract848.\n"
 "Source Field1 (16.96ac) belongs to Tyrease, source Field3 (12.50ac) belongs to Calvin;\n"
 "reusing the eventual independent farm image registration can efficiently map both.\n"
 "The source FSA county is not a physical field locator. Do not invent coordinates.\n")
index=OUT/"Batch2_Five_Farmer_QA.csv"
with index.open() as f:rows=list(csv.DictReader(f))
for rec in rows:
 if rec["farmer"]=="Calvin Blair":
  rec.update(status="SEARCHED_369_TILES_LOCATION_UNRESOLVED_SHARED_SOURCE_WITH_TYREASE_RILEY",
  source_registration="369 NAIP/Esri tiles, no nondegenerate match",
  blocker="Location unknown; FSA source exact pixel match with Tyrease Riley Farm3603 Tract848. Fields3 and1 can share future image registration.")
with index.open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
sfile=OUT/"BUILD_SUMMARY.json"
s=json.loads(sfile.read_text())
s.update(mappable_source_rows=rows,
 calvin_wide_search_tiles_loaded=369,
 calvin_wide_source_match="WEAK_OR_DEGENERATE_NOT_ACCEPTED",
 shared_source_crosswalk="Calvin Blair and Tyrease Riley exact same RGB FSA map pixels, Farm3603/Tract848",
 geographically_mapped_source_producers=3,admin_closed=1,remaining_followup_farmers_from_44=43)
sfile.write_text(json.dumps(s,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "Batch2 final reviewed five farmers: Christine Berry Zeigler Year2 Field1 completed; 43 farmers remain in prior queue.\n"
 "Joe Hilliard source Farm13859 Tract45814 Field36 registered; enrolled Field20 missing.\n"
 "Tywone Hilliard three source fields in three other Farm IDs registered; Year2 Farms1064/3826 missing.\n"
 "Calvin Blair source Farm3603 Field3 not georeferenced despite 369-tile search. Identical map shared with Tyrease Riley.\n"
 "Javeiann Spann source photos digitized but actual geographic field location unresolved.\n"
 "One farmer completed for Year2; three farmers with some accepted FSA source GIS; two source-only review folders.\n"
 "These approximate FSA photo traces are research planning layers, NOT legal surveys.\n")
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
with zipfile.ZipFile(BUNDLE) as z:
 n=z.namelist()
 assert sum(x.endswith('.shp') for x in n)==3
 assert sum(x.endswith('-FieldMap.pdf') for x in n)==3
 assert sum(x.endswith('README_NOT_GEOREFERENCED.txt') for x in n)==2
print("BATCH2_FINALIZED_AFTER_CALVIN",json.dumps(dict(source_farmers=3,closed=1,
   remaining=43,zip_bytes=BUNDLE.stat().st_size,calvin_tiles=369)),flush=True)
