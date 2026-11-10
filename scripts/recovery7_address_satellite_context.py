#!/usr/bin/env python3
"""Independent aerial context for manual interpretation; not field boundaries."""
from pathlib import Path
import json,requests,io,math
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery7_20261110/context"
OUT.mkdir(parents=True,exist_ok=True)
tasks=json.loads((ROOT/"analysis/recovery7_20261110/address_first_anchors.json").read_text())
r=6378137
def center(lon,lat):
 return (r*math.radians(lon),r*math.log(math.tan(math.pi/4+math.radians(lat)/2)))
def render(t,extent=2200):
 name=t["name"].replace(" ","_")
 anchor=t["unique_search_anchors"][0]
 x,y=center(anchor["lon"],anchor["lat"])
 bb=[x-extent/2,y-extent/2,x+extent/2,y+extent/2]
 url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
 q=dict(bbox=",".join(f"{v:.2f}" for v in bb),bboxSR=3857,imageSR=3857,size="1400,1400",format="jpg",f="image")
 response=requests.get(url,params=q,timeout=35);response.raise_for_status()
 im=Image.open(io.BytesIO(response.content)).convert("RGB")
 d=ImageDraw.Draw(im)
 # address center cross; NOT a field-location pin
 d.line([(688,700),(712,700)],fill="yellow",width=3)
 d.line([(700,688),(700,712)],fill="yellow",width=3)
 d.text((25,20),t["name"]+": GEOCODED ADDRESS CENTER (not confirmed field)",fill="white",stroke_width=3,stroke_fill="black")
 im.save(OUT/(name+"_address_center_aerial.jpg"),quality=80,optimize=True)
 print("CONTEXT",name,anchor["lon"],anchor["lat"],flush=True)
for task in tasks:
 try:render(task)
 except Exception as e:print("CONTEXT_ERROR",task["name"],str(e)[:150],flush=True)
