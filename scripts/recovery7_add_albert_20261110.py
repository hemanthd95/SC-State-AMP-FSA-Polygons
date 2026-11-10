#!/usr/bin/env python3
"""Append Albert Vareen Farm 9652/Tract 7769/Field 1 only after robust wide aerial match."""
import json,cv2,numpy as np,math
from pathlib import Path
from shapely.geometry import Polygon,mapping
from pyproj import Geod
ROOT=Path(__file__).resolve().parents[1]
DOC=ROOT/"geojson/counties/recovery7_address_registered_20261110.geojson"
QA=ROOT/"analysis/recovery7_20261110/accepted_polygon_qa.json"
WIDE=ROOT/"analysis/recovery7_20261110/Albert_Vareen/wide_registration_report.json"
reg=json.loads(WIDE.read_text())[0]
assert reg["valid"] and reg["inliers"]>=90 and reg["rmse_px"]<=1.5, "Independent source alignment insufficient"
H=np.asarray(reg["page_pdf_to_tile_H"],np.float64)
vertices=[[394,294],[577,386],[448,592],[303,467],[305,389]]
# The source is a 3171x4171-point photographed PDF. The traced reference
# was inspected at 912x1200; scale directly into original PDF page points.
pts=np.float32([[(x/912)*3171,(y/1200)*4171] for x,y in vertices])
warped=cv2.perspectiveTransform(pts[None],H)[0]
bb=reg["bbox_epsg3857"];N=reg["tile_size"];R=6378137.
ll=[]
for u,v in warped:
 mx=bb[0]+float(u)/N*(bb[2]-bb[0])
 my=bb[3]-float(v)/N*(bb[3]-bb[1])
 lon=mx/R*180/math.pi
 lat=(2*math.atan(math.exp(my/R))-math.pi/2)*180/math.pi
 ll.append([lon,lat])
poly=Polygon(ll)
assert poly.is_valid and not poly.is_empty
geod=Geod(ellps="WGS84")
ac=abs(geod.geometry_area_perimeter(poly)[0])/4046.8564224
assert abs(ac/10.13-1)<.15,("Area mismatch",ac)
rep=poly.representative_point()
address_lat,address_lon=34.207898180987,-79.244945120089
dist=math.hypot((rep.y-address_lat)*111000,(rep.x-address_lon)*111000*math.cos(math.radians(rep.y)))
assert dist<8000,("Too far from geocoded address",dist)
feature={
 "type":"Feature",
 "properties":{
   "producer":"Albert Vareen","county":"Marion","amp_roster_county":"Marion",
   "physical_county_basis":"Farm image registered to USGS NAIP after widening search from geocoded Excel address; FSA office county ignored",
   "farm_id":"9652","tract_id":"7769","field_id":"1",
   "fsa_reported_acres":10.13,"geodesic_acres":round(ac,4),
   "source_pdf":"Albert vareen_FSA_Map.pdf","source_page":1,
   "source_workbook_field_match":True,
   "registered_provider":reg["provider"],"registration_inliers":reg["inliers"],
   "registration_rmse_px":round(reg["rmse_px"],3),
   "distance_from_excel_address_m":round(dist,1),
   "area_difference_pct":round((ac/10.13-1)*100,2),
   "status":"REGISTERED_AERIAL_MATCH_APPROXIMATE_NOT_SURVEY",
   "geometry_quality":"MANUALLY_TRACED_FSA_SOURCE_AERIAL_MATCH_NOT_SURVEY",
   "registration_source":"analysis/recovery7_20261110/Albert_Vareen/wide_registration_report.json",
   "source_attribution":"FSA 2024 photo map and USGS NAIP reference",
   "map_source_date":"2026-11-10"
 },"geometry":mapping(poly)}
doc=json.loads(DOC.read_text())
if not any(f["properties"].get("farm_id")=="9652" and f["properties"].get("field_id")=="1" for f in doc["features"]):
 doc["features"].append(feature)
 DOC.write_text(json.dumps(doc,indent=2)+"\n")
report=json.loads(QA.read_text())
if not any(x.get("farmer")=="Albert Vareen" and x.get("field")=="1" for x in report["rows"]):
 report["rows"].append({"farmer":"Albert Vareen","farm":"9652","tract":"7769","field":"1",
   "area":10.13,"page":1,"enrolled_selected_field":True,
   "geodetic_acres":round(ac,4),"area_difference_pct":round((ac/10.13-1)*100,2),
   "image_match_inliers":reg["inliers"],"image_match_rmse_px":round(reg["rmse_px"],3),
   "distance_from_excel_address_m":round(dist,1),
   "status":"REGISTERED_AERIAL_MATCH_APPROXIMATE_NOT_SURVEY"})
 report["accepted_feature_count"]=len(doc["features"])
 QA.write_text(json.dumps(report,indent=2)+"\n")
print("ALBERT_GEOREFERENCED",round(ac,4),"acres",round(dist,1),"m from Excel address","features",len(doc["features"]),flush=True)
