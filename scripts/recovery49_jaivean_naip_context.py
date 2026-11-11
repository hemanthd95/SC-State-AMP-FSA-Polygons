#!/usr/bin/env python3
"""Source-image registration context for Jaivean Tylik Spann (Year2 AMPSC029).
Uploads only public orthoimage and road features, never an invented field boundary.
User supplied TWO FSA source photos to be registered separately:
3988/4673/field1 (9.35 acres, field4 0.29) and 9447/8142 (field IDs unprinted).
Excel farm address 1353 Rev. J. W. Carter Rd, Manning SC 29102 from Year1.
Year2 415 Drayton St is enrollment/mailing address, NOT the field center.
"""
from pathlib import Path
import io,json,requests,math
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery49_20261111/Jaivean_Spann"
OUT.mkdir(parents=True,exist_ok=True)
R=6378137.
SESSION=requests.Session();SESSION.headers.update({"User-Agent":"SCState-AMP-NAIP-Research/1.0"})
addresses=["1353 Rev J W Carter Rd, Manning, SC 29102",
 "1353 Reverend J W Carter Road, Manning, SC 29102",
 "1353 Rev JW Carter Rd, Manning, SC 29102"]
def req(url,params,timeout=30):
 r=SESSION.get(url,params=params,timeout=timeout);r.raise_for_status()
 return r
anchors=[]
for address in addresses:
 try:
  d=req("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
    dict(address=address,benchmark="Public_AR_Current",vintage="Current_Current",format="json"),25).json()
  for a in d.get("result",{}).get("addressMatches",[])[:3]:
   p=a["coordinates"];anchors.append(dict(source="US_CENSUS",lat=p["y"],lon=p["x"],matched=a.get("matchedAddress"),quality="address_match"))
 except Exception as e:print("GEOCODE_FAIL",address,str(e)[:200],flush=True)
 if anchors:break
if not anchors:
 try:
  d=req("https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
       dict(SingleLine=addresses[0],f="json",maxLocations=4),25).json()
  for a in d.get("candidates",[]):
   p=a["location"];anchors.append(dict(source="ArcGIS",lat=p["y"],lon=p["x"],matched=a["address"],score=a.get("score")))
 except Exception as e:print("ARCGIS_GEOCODE_ERROR",str(e),flush=True)
if not anchors:
 try:
  d=req("https://nominatim.openstreetmap.org/search",
       dict(q=addresses[0],format="jsonv2",limit=2),25).json()
  for a in d:anchors.append(dict(source="OSM",lat=float(a["lat"]),lon=float(a["lon"]),matched=a.get("display_name")))
 except Exception as e:print("OSM_ERROR",str(e)[:160],flush=True)
if not anchors:raise RuntimeError("NO_VERIFIED_FARM_ADDRESS_LOCATION — no origin for search")
anchor=anchors[0]
assert 33.0<anchor["lat"]<34.4 and -81.6<anchor["lon"]<-79.9
lon,lat=anchor["lon"],anchor["lat"]
x=R*math.radians(lon);y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))
print("ADDRESS_GEOCODE",json.dumps(anchor),flush=True)
# Optional geocoding of road ends to orient candidate farm cross intersections:
road_endpoints={}
for s in ["Moses Dingle Rd Manning SC","Silver Rd Manning SC","Rev JW Carter Rd Manning SC","Summerton Hwy Manning SC"]:
 try:
  d=req("https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
    dict(SingleLine=s,f="json",maxLocations=2),20).json()
  arr=[dict(lon=q["location"]["x"],lat=q["location"]["y"],match=q["address"],score=q.get("score"))
       for q in d.get("candidates",[]) if 33<q["location"]["y"]<34.4 and -81.6<q["location"]["x"]<-79.9]
  road_endpoints[s]=arr
 except Exception as e:road_endpoints[s]=[dict(error=str(e)[:100])]
source="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
esri="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",25)
tiles=[]
# Search 9 contiguous ~2.3km aerial tiles around actual address, plus context.
# Source 3988 has distinctive diagonal/horizontal rural-road junction.
offsets=[(0,0),(-1,0),(1,0),(0,1),(0,-1),
         (1,1),(-1,1),(1,-1),(-1,-1)]
for dx,dy in offsets:
 extent=2300;cx=x+dx*1850;cy=y+dy*1850
 bbox=[cx-extent/2,cy-extent/2,cx+extent/2,cy+extent/2]
 params=dict(bbox=",".join(f"{v:.3f}" for v in bbox),bboxSR=3857,imageSR=3857,
             size="1400,1400",format="jpg",f="image")
 for provider,url in [("USGS_NAIP",source)]:
  try:
   res=req(url,params,40)
   im=Image.open(io.BytesIO(res.content)).convert("RGB")
   assert im.size==(1400,1400)
   d=ImageDraw.Draw(im)
   d.rectangle((12,10,1090,58),fill=(20,20,20))
   d.text((25,20),f"Jaivean Spann | {provider} | Grid ({dx:+d},{dy:+d}) | 2.3 km",font=font,fill="white")
   if dx==0 and dy==0:
    d.ellipse((695,695,705,705),outline="yellow",width=4)
   nm=f"AddressGrid_{dx:+d}_{dy:+d}_{provider}.jpg"
   im.save(OUT/nm,quality=76,optimize=True)
   tiles.append(dict(file=nm,bbox_epsg3857=bbox,grid=[dx,dy],provider=provider))
   print("TILE",nm,flush=True)
  except Exception as e:print("TILE_ERROR",dx,dy,provider,str(e)[:180],flush=True)
# Figure to rapidly inspect 3x3 for appropriate road junction.
thumb=Image.new("RGB",(3*580,3*590),"white")
for row,dy in enumerate([1,0,-1]):
 for col,dx in enumerate([-1,0,1]):
  nm=f"AddressGrid_{dx:+d}_{dy:+d}_USGS_NAIP.jpg"
  p=OUT/nm
  if p.exists():
   im=Image.open(p);im.thumbnail((580,580));thumb.paste(im,(col*580,row*590))
thumb.save(OUT/"NAIP_Search_ContactSheet.jpg",quality=85,optimize=True)
(OUT/"address_search_qa.json").write_text(json.dumps(dict(
 source_fsa_images=["Javeiann_Spann_Field_1.jpeg","Javeiann_Spann_Field_2.jpeg"],
 source_fsa_field_1=dict(farm="3988",tract="4673",field="1",acres=9.35,adjacent_field_4_acres=.29),
 source_fsa_field_2=dict(farm="9447",tract="8142",unlabeled_fields=True),
 enrolled_year2=dict(farm="3988",tract="4673",field="1",acres=9.35),
 physical_field_search_address=addresses[0],other_enrollment_address="415 Drayton street Manning SC 29102 — NOT FIELD LOCATION",
 geocoded_addresses=anchors,other_road_geocodes=road_endpoints,
 tiles=tiles,warning="Geocoded ADDRESS is only search origin. None of these tiles yet establishes the field geometry."),indent=2)+"\n")
print("DONE",len(tiles),flush=True)
