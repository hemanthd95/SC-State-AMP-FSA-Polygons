#!/usr/bin/env python3
"""Antron Williams FSA Farm11990/Tract44081 Cinnabar Rd source-field recovery.
Use 13 digitized FSA ROAD CENTERLINE controls and 2026 US Census TIGER
Cinnabar road to find a geometrically distinctive matching section. Only
allow a source FIELD polygon if road-fit error and source acreage pass QA.
These are provisional ROAD-registered polygons, NOT NAIP/SIFT-verified.
"""
from pathlib import Path
import json,math,zipfile
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import minimize_scalar
from shapely.geometry import Polygon,mapping
from pyproj import Geod
ROOT=Path(__file__).resolve().parents[1]
CTX=ROOT/"analysis/recovery_20261111/Antron_Williams"
OUT=ROOT/"deliverables/antron_williams_cinnabar_20261111"
OUT.mkdir(parents=True,exist_ok=True)
GEO=ROOT/"geojson/counties/antron_williams_cinnabar_provisional_road_control_20261111.geojson"
ZIP=ROOT/"deliverables/Antron_Williams_Cinnabar_Road_Provisional_GIS_20261111.zip"
GEO.parent.mkdir(exist_ok=True,parents=True)
g=json.loads((CTX/"named_street_centerlines.geojson").read_text())
f=next(x for x in g["features"] if x["properties"]["name"]=="Cinnabar Rd")
cord=np.array(f["geometry"]["coordinates"],dtype=float)[::-1]
cos=np.cos(np.deg2rad(33.35))
W=np.column_stack([(cord[:,0]-cord[0,0])*111320*cos,
                   (cord[:,1]-cord[0,1])*111320])
Wlen=np.r_[0,np.cumsum(np.linalg.norm(np.diff(W,axis=0),axis=1))]
inter=interp1d(Wlen,W.T,bounds_error=False,fill_value="extrapolate")
# 13 source FSA road centerline anchors, from page5 map rendered 1039x1347.
# Source y increases downward; in map world north increases upward.
P=np.array([(99,213),(160,254),(220,300),(283,345),(349,388),
            (414,417),(482,449),(554,480),(628,514),(698,547),
            (766,573),(846,602),(944,636)],dtype=float)
P[:,1]*=-1
Pd=np.r_[0,np.cumsum(np.linalg.norm(np.diff(P,axis=0),axis=1))]
scale=.68 # meters per FSA raster pixel, consistent with 300-ft source scale bar
X=P*scale;X0=X-X.mean(axis=0)
def fit(s0,detail=False):
 if s0<0 or s0+Pd[-1]*scale>Wlen[-1]:return 10000
 T=inter(s0+Pd*scale).T
 Y=T-T.mean(axis=0)
 u,d,vt=np.linalg.svd(X0.T@Y)
 rot=u@vt
 if np.linalg.det(rot)<0:vt[-1,:]*=-1;rot=u@vt
 rmse=float(np.sqrt(np.mean(np.sum((X0@rot-Y)**2,axis=1))))
 rotdeg=float(np.degrees(np.arctan2(rot[0,1],rot[0,0])))
 if detail:return rmse,rotdeg,rot,T
 return rmse+abs(rotdeg)*.07
res=[]
for offset in range(0,int(Wlen[-1]-Pd[-1]*scale)-1,35):
 r=minimize_scalar(fit,bounds=(max(0,offset-35),min(Wlen[-1]-Pd[-1]*scale,offset+35)),method="bounded",
                   options=dict(xatol=.01,maxiter=80))
 if r.success:res.append((fit(r.x),r.x))
res.sort()
short=[]
for value,s0 in res:
 if any(abs(s0-x[1])<110 for x in short):continue
 short.append((value,s0))
 if len(short)==5:break
rmse,rotdeg,rot,T=fit(short[0][1],detail=True)
print("ROAD_REGISTRATION",json.dumps(dict(rmse_m=rmse,rotation_deg=rotdeg,alongroad_m=short[0][1],
 candidates=short)),flush=True)
if rmse>=4.4 or abs(rotdeg)>3 or len(short)<2 or short[1][0]<short[0][0]+1.4:
 raise RuntimeError("FSA road to TIGER road registration not uniquely validated")
centerX=X.mean(axis=0)
centerT=T.mean(axis=0)
def pixel_ll(x,y):
 wx,wy= ((np.array([float(x),-float(y)])*scale-centerX)@rot+centerT)
 return [float(cord[0,0]+wx/(111320*cos)),float(cord[0,1]+wy/111320)]
FIELDS={
 "7":{"acres":1.23,"points":[(190,137),(225,143),(257,159),(222,285),(172,261),(142,235),(160,175)]},
 "18":{"acres":1.68,"points":[(882,438),(894,458),(887,482),(826,573),(798,582),(748,564),(748,503),(774,452),(860,432)]},
 "19":{"acres":.41,"points":[(804,531),(825,541),(821,595),(774,657),(745,632),(734,610),(747,566)]},
 "20":{"acres":1.71,"points":[(620,714),(723,739),(671,844),(638,890),(584,829),(610,728)]}
}
GEOD=Geod(ellps="WGS84")
features=[];table=[];reject=[]
for field,rec in FIELDS.items():
 poly=Polygon([pixel_ll(x,y) for x,y in rec["points"]])
 if not poly.is_valid:raise RuntimeError("Invalid field polygon "+field)
 area=abs(GEOD.geometry_area_perimeter(poly)[0])/4046.8564224
 delta=100*(area/rec["acres"]-1)
 row=dict(field=field,source_fsa_acres=rec["acres"],
   trace_geodetic_acres=round(area,4),acreage_difference_pct=round(delta,2))
 if abs(delta)>15:
  row["status"]="REJECTED_AREA_DISAGREEMENT";reject.append(row)
  print("EXCLUDED_FIELD",row,flush=True)
  table.append(row)
  continue
 row["status"]="PROVISIONAL_ROAD_REGISTERED_NOT_SIFT_VALIDATED";table.append(row)
 features.append({"type":"Feature","properties":{
   "producer":"Antron Williams","county":"Orangeburg","farm_id":"11990",
   "tract_id":"44081","field_id":field,"roster_county":"Orangeburg",
   "fsa_acres":rec["acres"],"geodetic_acres":round(area,4),
   "acreage_difference_pct":round(delta,2),
   "source_pdf":"Anthron Williams_FSA_Map.pdf, page 5 map only",
   "source_road":"Cinnabar Rd","source_page":5,
   "source_workbook_field_match":field in ("6","7"),
   "registration_method":"13 visually digitized FSA road points fit to 2026 US Census TIGER Cinnabar road curve, north-up 0.68m per source image pixel",
   "registration_control_rmse_m":round(rmse,3),
   "registration_rotation_deg":round(rotdeg,3),
   "registration_quality":"PROVISIONAL_ROAD_CURVE_FIT_NO_INDEPENDENT_NAIP_IMAGE_FEATURE_VALIDATION",
   "field_status":"PROVISIONAL_FSA_FIELD_OUTLINE_NOT_SURVEY",
   "source_attribute_warning":"Enrolled workbook Field7 covered; Field6 is not established; FSA map Field61 may be a distinct field"
  },"geometry":mapping(poly)})
if not any(x["properties"]["field_id"]=="7" for x in features):
 raise RuntimeError("Unable to trace enrolled Field7")
geojson={"type":"FeatureCollection","name":"Antron_Williams_Cinnabar_Page5_Provisional",
         "features":features}
GEO.write_text(json.dumps(geojson,indent=2)+"\n")
(OUT/"REGISTERED_FIELDS.geojson").write_text(json.dumps(geojson,indent=2)+"\n")
report={"farm_id":"11990","tract_id":"44081",
  "source_page":5,"source_road":"Cinnabar Rd",
  "control_source":"US Census TIGER road geometry",
  "source_FSA_road_pixels":P.tolist(),"road_line_fit_rmse_m":round(rmse,4),
  "road_line_rotation_deg":round(rotdeg,4),
  "source_scale_m_per_pixel":scale,
  "road_fit_alongroad_m":short[0][1],
  "second_best_candidate_error":short[1][0],
  "qa":table,
  "rejected":reject,
  "limitations":["Printed county not used as farm locator",
   "Independent NAIP imagery feature matching not confirmed; positional accuracy remains provisional",
   "The road-line fit is a georegistration control, not independent verification of field ownership",
   "The Year2 roster Field6 is NOT confirmed from this page",
   "Do not count farmer as completed from source-only or provisional field labels"]
 }
(OUT/"Cinnabar_Georegistration_QA.json").write_text(json.dumps(report,indent=2)+"\n")
import publish_per_farmer_weekley_style_20261110 as pub
pub.OUT=OUT
qa=pub.process(("Antron Williams","Orangeburg"),features)
(OUT/"map_generation_qa.json").write_text(json.dumps(qa,indent=2)+"\n")
(OUT/"README_START_HERE.txt").write_text(
  "ANTRON WILLIAMS - Cinnabar Rd - PROVISIONAL GEOGRAPHIC REGISTRATION\n"
  "FSA Farm11990 Tract44081; source page 5, Fields7,18,20 accepted with provisional road controls.\n"
  "Field19 excluded due >15% FSA acreage discrepancy (see QA).\n"
  "Road curve registered to 2026 TIGER road (13 points, ~3.4m fitting RMSE) and source 300-ft scale.\n"
  "No independent aerial SIFT match; NO owner/survey/legal accuracy claim.\n"
  "Year2 enrollment Field6 is NOT completed. Field7 is preliminary pending independent validation.\n"
  "FSA printed administrative county not used as field location evidence.\n"
  "Source tax records excluded from delivery.\n")
ZIP.parent.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
 for p in sorted(OUT.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(OUT.parent))
print("FINAL",json.dumps(dict(geometries=len(features),accepted_fields=[f["properties"]["field_id"] for f in features],
  rejected_fields=[v["field"] for v in reject],archive_bytes=ZIP.stat().st_size,
  map_qa=qa)),flush=True)
