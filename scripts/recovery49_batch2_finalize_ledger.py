#!/usr/bin/env python3
"""Correct Batch2 completion ledger based on direct visual inspection of the
FSA original photo footer: Christine Berry Zeigler, Farm1271, Tract469,
source Field1 10.51ac. Distinguish approximate research mapping from survey.
Repack the same combined ZIP so published QA is internally consistent.
"""
import csv,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/recovery49_batch2_five_20261111"
BUNDLE=ROOT/"deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip"
with zipfile.ZipFile(BUNDLE) as z:
 for rec in z.infolist():
  if rec.is_dir():continue
  p=ROOT/"deliverables"/rec.filename
  p.parent.mkdir(parents=True,exist_ok=True)
  p.write_bytes(z.read(rec))
qa_files=list(OUT.rglob("SOURCE_FIELD_QA.json"))
assert len(qa_files)==1,qa_files
qa_file=qa_files[0]
qa=json.loads(qa_file.read_text())
assert qa["source_farm_tract_field"]=="1271/469/1" and abs(qa["geodetic_acres"]-11.1279)<.05
qa.update(
 fsa_farm_tract_visually_confirmed_from_source_photo_footer=True,
 source_photo_footer_farm="1271",source_photo_footer_tract="469",
 source_photo_field_label="1",source_photo_fsa_acres=10.51,
 enrollment_qa="CLOSED_AGAINST_KNOWN_YEAR2_FARM_TRACT_FIELD",
 approximate_geometry_is_survey=False,
 farmer_administratively_closed_against_year2_record=True)
qa_file.write_text(json.dumps(qa,indent=2)+"\n")
status_file=qa_file.parent/"README_STATUS_FIRST.txt"
status_file.write_text(
 "Christine Berry Zeigler YEAR2 TARGET COMPLETED: Farm1271 Tract469 Field1, 10.51 FSA acres.\n"
 "Source Farm1271 and Tract469 confirmed by direct visual inspection of original photographed FSA footer.\n"
 "NAIP registration: 217 matches, 1.2803 pixel residual; mapped approximate area 11.1279 ac, difference +5.88%.\n"
 "Field located in Orangeburg County from official census polygons; printed FSA office county ignored.\n"
 "Research-only field geometry; NOT a cadastral or legal survey.\n")
rows_path=OUT/"Batch2_Five_Farmer_QA.csv"
with rows_path.open() as f:rows=list(csv.DictReader(f))
assert len(rows)==5
for r in rows:
 if r["farmer"]=="Christine Berry Zeigler":
  r["administratively_closed"]="True"
  r["blocker"]="None for the known Year2 Farm1271/Tract469/Field1; approximate photo-boundary quality recorded separately"
  r["status"]="COMPLETED_KNOWN_YEAR2_FIELD_APPROXIMATE_GEOREGISTRATION"
with rows_path.open("w",newline="") as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]))
 w.writeheader();w.writerows(rows)
summary_path=OUT/"BUILD_SUMMARY.json"
s=json.loads(summary_path.read_text())
s.update(admin_closed=1,closed_year2_farmers=["Christine Berry Zeigler"],
 remaining_followup_farmers_from_44=43,baseline_outstanding_year2=44,
 year2_farmers_geographically_mapped=1,
 year2_completion_rule="Registered source Farm1271 Tract469 Field1 matched to enrolled target; printed FSA source footer visually confirmed. Mapped acreage may differ up to 25% and is not survey accuracy.",
 mappable_source_rows=rows)
summary_path.write_text(json.dumps(s,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
 "Batch2 SC State AMP: five farmers. ONE known Year2 farm completed: Christine Berry Zeigler.\n"
 "Two producers have georeferenced source field polygons: Christine (1) and Tywone Hilliard (3).\n"
 "Tywone source Farm IDs do not match enrolled Farms1064/3826. His enrollment remains OPEN.\n"
 "Joe Hilliard source Farm6528 differs from selected Farm13859; alternate Farm13859 photo lacks enrolled Field20.\n"
 "Calvin Blair and Javeiann Spann still lack accepted field geographic locations.\n"
 "Working farmer queue 44 -> 43, pending separate year-wide field-level audit.\n"
 "Approximate FSA source polygons for research GIS, not legal surveys.\n")
with zipfile.ZipFile(BUNDLE,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
with zipfile.ZipFile(BUNDLE) as z:
 assert sum(n.endswith(".shp") for n in z.namelist())==2
print("BATCH2_LEDGER_CORRECTED",json.dumps(dict(closed=1,queue=43,zip_bytes=BUNDLE.stat().st_size)),flush=True)
