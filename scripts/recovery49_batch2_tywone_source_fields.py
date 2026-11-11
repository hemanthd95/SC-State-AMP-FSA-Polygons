#!/usr/bin/env python3
"""Extend Batch2 with three *source-only* Tywone Hilliard fields.
Georegistration is strong but FSA Farm IDs differ from Year2 enrollment,
so the three shapes are NOT used to close Farms 1064 or 3826.
Source reference coords are in the 620x604 displayed aerial crop shown
from a 980x1268 original source page (xorig=140+1.25*x; yorig=130+1.25*y).
"""
from pathlib import Path
import json,math,zipfile,io,tempfile,requests,shutil,csv
import numpy as np,cv2,shapefile
from shapely.geometry import Polygon,shape,mapping
from pyproj import Geod
import publish_per_farmer_weekley_style_20261110 as atlas
ROOT=Path(__file__).resolve().parents[1]
QROOT=ROOT/"analysis/recovery49_20261111/batch2/source_page_registration/Tywone_Hilliard"
BASE=ROOT/"deliverables/recovery49_batch2_five_20261111"
ZIP=ROOT/"deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip"
GEO=ROOT/"geojson/counties/recovery49_batch2_tywone_source_fields_20261111.geojson"
GEO.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ZIP) as z:
 for item in z.infolist():
  if item.is_dir():continue
  target=ROOT/"deliverables"/item.filename
  target.parent.mkdir(parents=True,exist_ok=True)
  target.write_bytes(z.read(item))
state=json.loads((QROOT/"source_registration_QA.json").read_text())
valid={x["source_page"]:x for x in state["results"] if
 x["pdf"]=="Tywone Hillard_FSA_Map.pdf" and x["valid"] and
 x["inliers"]>=150 and x["rmse_px"]<1.5 and x["provider"]=="USGS_NAIP"}
assert set(valid)=={1,2,3}
# Deliberately map only clearly visible labeled fields; source hand-drawn
# 2024 FSA paper boundaries are not land surveys.
ENTRIES=[
 dict(page=1,farm="3873",tract="3895",field="4",ref_ac=1.93,
  poly=[[371,269],[399,246],[432,245],[448,271],[446,299],[422,310],[376,315]]),
 dict(page=2,farm="4261",tract="5953",field="2",ref_ac=2.10,
  poly=[[262,243],[285,234],[320,246],[352,273],[370,304],[347,322],[319,298],[282,282],[261,262]]),
 dict(page=3,farm="960",tract="3812",field="1",ref_ac=3.41,
  poly=[[294,301],[434,282],[437,294],[473,316],[478,325],[363,342],[293,350],[287,333]])
]
R=6378137.;GEOD=Geod(ellps="WGS84")
def poly_from_screen(src,rec):
 H=np.asarray(rec["source_page_pdf_pts_to_tile_H"],dtype=np.float64)
 pts=np.float32([[(140+1.25*x)/1.6,(130+1.25*y)/1.6] for x,y in src])
 warped=cv2.perspectiveTransform(pts[None],H)[0]
 b=rec["tile_bbox_epsg3857"];S=rec["tile_size_px"]
 coords=[]
 for u,v in warped:
  mx=b[0]+float(u)/S*(b[2]-b[0]);my=b[3]-float(v)/S*(b[3]-b[1])
  coords.append([math.degrees(mx/R),math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)])
 geom=Polygon(coords)
 assert geom.is_valid and not geom.is_empty
 return geom
geometries=[poly_from_screen(x["poly"],valid[x["page"]]) for x in ENTRIES]
# Full official SC county shapes; do not trust printed administrative county.
response=requests.get("https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip",timeout=60)
response.raise_for_status()
with tempfile.TemporaryDirectory() as td:
 with zipfile.ZipFile(io.BytesIO(response.content)) as z:z.extractall(td)
 reader=shapefile.Reader(str(next(Path(td).glob("*.shp"))))
 county_geos=[(r.as_dict()["NAME"],shape(g.__geo_interface__)) for g,r in zip(reader.shapes(),reader.records()) if r.as_dict().get("STATEFP")=="45"]
assert len(county_geos)==46
def county(g):
 a=[name for name,geo in county_geos if geo.covers(g.representative_point())]
 assert len(a)==1,a
 return a[0]
features=[];qa=[]
for record,geom in zip(ENTRIES,geometries):
 ac=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
 dif=100*(ac/record["ref_ac"]-1)
 assert abs(dif)<=25,(record["field"],ac,dif)
 c=county(geom);rec=valid[record["page"]]
 props=dict(producer="Tywone Hilliard",county=c,roster_county="Orangeburg",
   farm_id=record["farm"],tract_id=record["tract"],field_id=record["field"],
   source_fsa_acres=record["ref_ac"],geodesic_acres=round(ac,4),
   acreage_difference_pct=round(dif,2),
   source_pdf="Tywone Hillard_FSA_Map.pdf",source_page=record["page"],
   source_map_year=2024,
   source_workbook_field_match=False,
   registered_provider="USGS_NAIP",
   image_registration_inliers=rec["inliers"],registration_rmse_px=rec["rmse_px"],
   status="REGISTERED_SOURCE_FIELD_YEAR2_FARM_ID_MISMATCH",
   registration_method="SIFT georectification from scanned FSA photo to USGS NAIP",
   physical_county_basis="Official 2025 US Census county spatial boundary; printed FSA office county ignored",
   geometry_quality="PHOTO_DIGITIZED_APPROXIMATE_NOT_SURVEY",
   note="Year2 records include Farm1064 and Farm3826; source Farm IDs differ. Not a completed enrolled farm.")
 features.append({"type":"Feature","properties":props,"geometry":mapping(geom)})
 qa.append(dict(page=record["page"],farm=record["farm"],tract=record["tract"],
   field=record["field"],source_acres=record["ref_ac"],mapped_acres=round(ac,4),
   diff_pct=round(dif,2),registered_matches=rec["inliers"],
   rmse_px=rec["rmse_px"],physical_county=c))
assert len(set(x["properties"]["county"] for x in features))==1
real_county=features[0]["properties"]["county"]
GEO.write_text(json.dumps({"type":"FeatureCollection","name":"Tywone_Hilliard_2024_FSA_Source_Only",
 "features":features},indent=2)+"\n")
atlas.OUT=BASE
mapqa=atlas.process(("Tywone Hilliard",real_county),features)
assert mapqa["county_map_status"]=="CREATED" and mapqa["field_map_status"]=="CREATED",mapqa
folder=BASE/real_county/atlas.human_folder("Tywone Hilliard")
(folder/"SOURCE_ONLY_NOT_YEAR2_ENROLLED_QA.json").write_text(json.dumps(dict(
 source_fields=qa,map_qa=mapqa,
 enrolled_year2_farms=["1064","3826"],
 source_farm_ids=["3873","4261","960"],farmer_administratively_closed=False,
 caveat="Three georeferenced photos are DIFFERENT FSA farms than the enrolled targets; never silently substitute."),indent=2)+"\n")
(folder/"README_STATUS_FIRST.txt").write_text(
 "Tywone Hilliard: THREE 2024 FSA SOURCE FIELDS GEOREFERENCED; YEAR2 ENROLLMENT OPEN.\n"
 "Source map1 Farm3873 Tract3895 Field4, source map2 Farm4261 Tract5953 Field2,\n"
 "source map3 Farm960 Tract3812 Field1. All from scans matched to USGS NAIP imagery.\n"
 "Year2 asks for Farms1064 and3826, not covered by these source PDF pages.\n"
 "Approximate photo traces, not legal cadastral surveys.\n"
 "One producer EPSG:4326 shapefile, one county topo map, three satellite close-up pages.\n")
# Remove original empty Tywone review folder; now same participant has actual source polygons.
old=BASE/"SOURCE_REVIEW_ONLY"/"L-Tywone_Hilliard"
if old.exists():shutil.rmtree(old)
qa_csv=BASE/"Batch2_Five_Farmer_QA.csv"
with qa_csv.open() as f: rows=list(csv.DictReader(f))
for r in rows:
 if r["farmer"]=="Tywone Hilliard":
  r.update(status="THREE_SOURCE_FIELDS_GEOREFERENCED_ENROLLMENT_FARMS_NOT_MATCHED",
   accepted_polygon_count="3",physical_county=real_county,
   target="SOURCE 3873/3895/4,4261/5953/2,960/3812/1",
   area_ac=f"{sum(x['mapped_acres'] for x in qa):.3f}",
   source_registration="188-232 NAIP matches on 2024 pages",
   administratively_closed="False",
   blocker="Year2 Farms1064 and3826 still missing exact georeferenced enrolled field; different FSA farm IDs")
with qa_csv.open("w",newline="") as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
summary_p=BASE/"BUILD_SUMMARY.json"
summary=json.loads(summary_p.read_text())
summary["source_review_only"]=3
summary["geographically_mapped_source_producers"]=2
summary["year2_farmers_geographically_mapped"]=1
summary["additional_source_only_fields"]=["Tywone 3873/3895/4","Tywone 4261/5953/2","Tywone 960/3812/1"]
summary["ty_hilliard_note"]="Three source FSA farms 2024 geographically registered, but none matches Year2 Farm1064 or3826. Farmer NOT CLOSED."
summary["mappable_source_rows"]=rows
summary_p.write_text(json.dumps(summary,indent=2)+"\n")
(BASE/"README_START_HERE.txt").write_text(
 "Batch2 five SC AMP farmers. Christine: source- and roster-matched Farm1271/Tract469/Field1, registered.\n"
 "Tywone: 3 photographed-source FSA fields on other Farm IDs registered, NOT Year2 completed.\n"
 "Joe, Calvin, Javeiann: source-only QA; no accepted enrolled field polygon yet.\n"
 "GIS is approximate for research planning; not legal surveys; ignore FSA printed office counties.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=4) as z:
 for p in sorted(BASE.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(BASE.parent))
print("BATCH2_TYWONE_SOURCE_FIELDS",json.dumps(dict(fields=qa,physical_county=real_county,
 maps=mapqa,zip_bytes=ZIP.stat().st_size,year2_closed=False)),flush=True)
