#!/usr/bin/env python3
"""Candidate Cinnabar Road registration:
Image-free projection of *source-page traced field polygons* onto
independently mapped road candidate segments. All are hypotheses until
aerial background edges confirm an actual geographic match.
"""
import json,io,math,requests
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import shape,Point
from shapely.ops import transform
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery_20261111/Antron_Williams/Cinnabar_Candidate_Registration"
OUT.mkdir(parents=True,exist_ok=True)
SOURCE=ROOT/"analysis/recovery_20261111/Antron_Williams/named_street_centerlines.geojson"
raw=json.loads(SOURCE.read_text())["features"]
roads=[x for x in raw if x["properties"]["name"]=="Cinnabar Rd"]
# Candidates determined independently from 2026 US Census TIGER shape;
# all are roughly 600-m sections with average southeast bearing ~27 degrees.
CANDIDATES=[
 ("western_bend", -80.755720,33.366365),
 ("western_bend_plus60m",-80.755119,33.366167),
 ("mid_straight", -80.745626,33.362795),
 ("mid_straight_plus80m", -80.744488,33.362288),
 ("east_bend",-80.723688,33.348135)]
R=6378137.
WM=Transformer.from_crs(4326,3857,always_xy=True)
fields={
 "7":{"acres":1.23,"points":[(190,137),(225,143),(248,152),(257,160),(243,199),(222,286),(177,264),(142,235),(161,174)]},
 "18":{"acres":1.68,"points":[(775,451),(809,452),(864,431),(881,437),(894,459),(888,479),(863,524),(825,573),(773,594),(748,566),(748,503)]},
 "19":{"acres":.41,"points":[(748,565),(822,592),(776,658),(746,632),(734,612)]},
 "20":{"acres":1.71,"points":[(615,715),(642,715),(696,738),(721,742),(771,657),(742,705),(699,782),(670,845),(637,891),(634,874),(610,862),(584,828),(595,788)]}
}
colors={"7":"#FA2929","18":"#24FCBB","19":"#FFB13B","20":"#D656F8"}
S=requests.Session();S.headers["User-Agent"]="SC-State-AMP/2026 independent FSA alignment QA"
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',28)
pixels_per_m=1500/1450
extent=1450
def get(center):
 cx,cy=WM.transform(center[1],center[2])
 bbox=[cx-extent/2,cy-extent/2,cx+extent/2,cy+extent/2]
 url="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
 q=dict(bbox=",".join(f"{v:.2f}" for v in bbox),bboxSR=3857,imageSR=3857,size="1500,1500",format="jpg",f="image")
 r=S.get(url,params=q,timeout=45);r.raise_for_status()
 return Image.open(io.BytesIO(r.content)).convert("RGB"),bbox
def px(mx,my,bbox):
 return ((mx-bbox[0])/(bbox[2]-bbox[0])*1500,(bbox[3]-my)/(bbox[3]-bbox[1])*1500)
out=[]
for name,lon,lat in CANDIDATES:
 try:im,bbox=get((name,lon,lat))
 except Exception as e:print("CANDIDATE_ERROR",name,str(e)[:180],flush=True);continue
 d=ImageDraw.Draw(im)
 for r in roads:
  g=shape(r["geometry"])
  part=g.geoms if g.geom_type=="MultiLineString" else [g]
  for line in part:
   vertices=[px(*WM.transform(x,y),bbox) for x,y in line.coords]
   d.line(vertices,fill="#FADD00",width=3,joint="curve")
 # Source printed scale bar = 300 ft / 136 image px in 1.7x render.
 # Source-up = geographic north; map page appears north-up.
 fsa_px_to_merc_m=(300*0.3048/136)/math.cos(math.radians(lat))
 # map road control pixel approx (x500,y430) aligned to road candidate center
 refx,refy=500,430
 cx,cy=WM.transform(lon,lat)
 pp={}
 for field,entry in fields.items():
  transformed=[]
  for x,y in entry["points"]:
   mx=cx+(x-refx)*fsa_px_to_merc_m
   my=cy-(y-refy)*fsa_px_to_merc_m
   transformed.append(px(mx,my,bbox))
  d.polygon(transformed,fill=None,outline=colors[field],width=5)
  meanx=sum(x for x,y in transformed)/len(transformed);meany=sum(y for x,y in transformed)/len(transformed)
  d.text((meanx,meany),field,font=font,fill="white",stroke_width=4,stroke_fill="black")
  pp[field]=transformed
 d.text((20,20),f"{name} Cinnabar - CANDIDATE ONLY - SOURCE TRACE OVER NAIP",
    fill="white",stroke_width=3,stroke_fill="black")
 im.save(OUT/(name+"_provisional_trace_overlay.jpg"),quality=86,optimize=True)
 out.append(dict(name=name,anchor_WGS84=[lon,lat],georeference_model="source FSA scale bar and north-up with one road control (candidate only)",bbox_epsg3857=bbox))
 print("CANDIDATE",name,lon,lat,flush=True)
(OUT/"candidate_summary.json").write_text(json.dumps({"status":"ROAD_ONLY_CANDIDATES_NOT_YET_REGISTERED_FIELDS","candidates":out,"warning":"Do not publish any candidate geometry as accepted from this QA without matching aerial field boundaries."},indent=2))
