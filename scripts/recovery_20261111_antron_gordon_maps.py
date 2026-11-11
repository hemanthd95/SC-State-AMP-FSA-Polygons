#!/usr/bin/env python3
"""Digitize Antron Williams' Gordon Drive FSA page against independently
georeferenced NAIP road controls. Approximate planning polygons, not survey.
No W-9 or confidential producer paperwork is used or uploaded.
"""
from pathlib import Path
import io,json,math,zipfile,os,sys
import cv2,numpy as np
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import Polygon,mapping,shape
from shapely.ops import unary_union
from pyproj import Geod,Transformer

ROOT=Path(__file__).resolve().parents[1]
CTX=ROOT/"analysis/recovery_20261111/Antron_Williams"
GEO=ROOT/"geojson/counties/antron_williams_gordon_manual_road_registration_20261111.geojson"
DEST=ROOT/"deliverables/antron_williams_gordon_20261111"
ZIP=ROOT/"deliverables/Antron_Williams_Gordon_Drive_Provisional_GIS_20261111.zip"
DEST.mkdir(parents=True,exist_ok=True);GEO.parent.mkdir(parents=True,exist_ok=True)
R=6378137.0;GEOD=Geod(ellps="WGS84")
# Independent road controls manually identified on 2026 FSA page 7 and
# NAIP 1400m context. Source image was rendered at 1039x1347.
# FSA pixel x,y -> geographically referenced NAIP image x,y.
# Control A: north-south unnamed road / Gordon Dr intersection
# Control B: roadway point north of intersection
# Control C: Gordon Dr road center southwest of intersection
FSA_CONTROLS=np.float32([(715,566),(655,369),(400,815)])
NAIP_CONTROLS=np.float32([(820,690),(790,568),(655,820)])
A=cv2.getAffineTransform(FSA_CONTROLS,NAIP_CONTROLS)
context=json.loads((CTX/"road_search_summary.json").read_text())
ref=next(x for x in context["map_downloads"] if x["file"]=="Gordon_Dr_USGS_NAIP_1400m.jpg")
bbox=ref["bbox_epsg3857"];size=1500
fields={
 "61":{"fsa_acres":3.03,"points":[(597,378),(660,369),(678,464),(696,519),(716,565),(685,592),(635,631),(585,670),(548,705),(496,744),(414,803),(352,767),(374,732),(395,689),(459,652),(502,598),(531,574),(473,552),(473,486),(469,453),(594,427)]},
 "3":{"fsa_acres":1.05,"points":[(543,734),(601,690),(661,647),(725,596),(713,792),(685,804),(641,820),(611,812),(572,766)]},
 "16":{"fsa_acres":1.05,"points":[(670,269),(775,352),(855,405),(863,430),(834,465),(752,528),(741,520),(712,457),(699,399)]}
}
def lonlat(pixel):
 ux,uy=pixel
 x=bbox[0]+float(ux)/size*(bbox[2]-bbox[0])
 y=bbox[3]-float(uy)/size*(bbox[3]-bbox[1])
 lon=math.degrees(x/R)
 lat=math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)
 return (lon,lat)
features=[];rows=[]
overlay=Image.open(CTX/"Gordon_Dr_USGS_NAIP_1400m.jpg").convert("RGBA")
layer=Image.new("RGBA",overlay.size,(0,0,0,0));d=ImageDraw.Draw(layer)
colors={"61":"#EE4B56","3":"#37C8F0","16":"#DAB22A"}
for name,f in fields.items():
 points=cv2.transform(np.float32(f["points"])[None],A)[0]
 poly=Polygon([lonlat(z) for z in points])
 if not poly.is_valid or poly.is_empty:raise RuntimeError("Invalid polygon: "+name)
 acres=abs(GEOD.geometry_area_perimeter(poly)[0])/4046.8564224
 dif=100*(acres/f["fsa_acres"]-1)
 if abs(dif)>18:raise RuntimeError(f"Area gate failed for FSA Field {name}: {acres:.3f}")
 if not (-80.77<poly.centroid.x<-80.74 and 33.36<poly.centroid.y<33.39):
  raise RuntimeError("Polygon outside expected independently identified Gordon Rd neighborhood")
 pp=[tuple(map(float,p)) for p in points]
 d.polygon(pp,fill=(245,63,70,72),outline=colors[name],width=5)
 centroid=np.array(points).mean(axis=0)
 d.text((float(centroid[0]),float(centroid[1])),name,
        fill="white",stroke_width=3,stroke_fill="black",
        font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",28))
 row={"field_id":name,"source_printed_acres":f["fsa_acres"],
      "geodesic_trace_acres":round(acres,4),"acreage_difference_pct":round(dif,2),
      "source_image_pixel_vertices":f["points"],
      "naip_reference_pixel_vertices":points.tolist(),
      "status":"PROVISIONAL_GEOREFERENCED_ROAD_CONTROL_NOT_INDEPENDENT_SIFT_VALIDATION"}
 rows.append(row)
 features.append({"type":"Feature","properties":{
    "producer":"Antron Williams","farm_id":"11990","tract_id":"44081","field_id":name,
    "county":"Orangeburg","roster_county":"Orangeburg",
    "fsa_acres":f["fsa_acres"],"geodesic_acres":round(acres,4),
    "acreage_difference_pct":round(dif,2),"source_page":7,
    "source_pdf":"Anthron Williams_FSA_Map.pdf (FSA map page only; tax pages excluded)",
    "source_road":"Gordon Dr",
    "source_workbook_field_match":False if name in ("61","3","16") else True,
    "fsa_field_type":"SOURCE_MAP_VISIBLE_WORKBOOK_ID_REQUIRES_RECONCILIATION",
    "registration_method":"Three independent FSA-road to geographically referenced USGS NAIP control points, affine",
    "registration_reference":"USGS NAIP and Census TIGERweb Orangeburg road geometry",
    "registration_quality":"PROVISIONAL_MANUAL_CONTROL; not survey quality; visual and ground verification needed",
    "road_control_count":3,
    "geometry_status":"GIS_APPROXIMATE_NAIP_REGISTERED_FSA_TRACE_PROVISIONAL"
    },"geometry":mapping(poly)})
final=Image.alpha_composite(overlay,layer).convert("RGB")
final.save(DEST/"Gordon_Drive_FSA_Field_Registration_QA.jpg",quality=89,optimize=True)
doc={"type":"FeatureCollection","name":"Antron_Williams_Gordon_Three_Source_Fields_Provisional_20261111",
 "features":features}
GEO.write_text(json.dumps(doc,indent=2)+"\n")
(DEST/"REGISTERED_FIELDS.geojson").write_text(json.dumps(doc,indent=2)+"\n")
qa={
 "source":"FSA Farm11990 Tract44081 map page 7; confidential attachment pages excluded",
 "road":"Gordon Dr", "source_page":7, "workbook_expected_fields":["6","7"],
 "source_map_visible_fields":["61","3","16"],
 "registration_method":"Manual three-point FSA-to-NAIP road intersection control",
 "FSA_pixel_points":FSA_CONTROLS.tolist(),"NAIP_pixel_points":NAIP_CONTROLS.tolist(),
 "affine_FSA_pixel_to_NAIP_pixel":A.tolist(),
 "NAIP_bbox_EPSG3857":bbox,"NAIP_image_pixels":[1500,1500],
 "field_quality":rows,
 "limitations":["The apparent Field 61 identifier has not been proven to be workbook Field 6",
   "Source FSA map field 7 is on separate Cinnabar Road page; not covered in this layer",
   "Registration has not been independently confirmed with SIFT or a land survey",
   "No enrollment target is marked complete until exact farm/tract/field assignment is reconciled"]
}
(DEST/"QA_Provisional_Gordon_Registration.json").write_text(json.dumps(qa,indent=2)+"\n")
# Render Weekley-style two-map farmer folder by reusing existing tested generator.
import publish_per_farmer_weekley_style_20261110 as pub
pub.OUT=DEST
result=pub.process(("Antron Williams","Orangeburg"),features)
(DEST/"map_generation_qa.json").write_text(json.dumps(result,indent=2)+"\n")
(DEST/"README_START_HERE.txt").write_text(
 "SC State AMP - Antron Williams Gordon Drive parcel outlines (PROVISIONAL)\n"
 "FSA Farm11990, Tract44081; source map page7 Fields61/3/16.\n"
 "Do NOT claim these match Year2 enrollment Fields6/7 without independent reconciliation.\n"
 "Three control points position map near Gordon Dr in Orangeburg, about 1%-2% acreage discrepancy.\n"
 "No source tax paperwork included. Field shapefile is approximate EPSG:4326; not a survey.\n"
 "Gordon_Drive_FSA_Field_Registration_QA.jpg shows source fields on USGS NAIP aerial.\n"
 "See the generated L-Williams, Antron folder for shapefile, CountyMap.pdf, FieldMap.pdf.\n")
with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as z:
 for p in sorted(DEST.rglob("*")):
  if p.is_file():z.write(p,p.relative_to(DEST.parent))
print("COMPLETE_GORDON_GIS",len(features),"files",ZIP.stat().st_size,"map_quality",result,flush=True)
