#!/usr/bin/env python3
"""Recover address-first anchor hints for seven AMPs; FSA printed counties are ignored.
The address determines SEARCH area, not field location or polygon.
"""
import json,requests,math,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"analysis/recovery7_20261110"
OUT.mkdir(parents=True,exist_ok=True)
TARGETS=[
 {"name":"Angale Johnson","roster_county":"Horry","address":"5937 Primrose Drive Galivants Ferry, SC 29544","workbook_lat":34.0470542,"workbook_lon":-79.0934566,"fields":["22560/17266/1","22564/17268/2","22564/17265/13"],"source_pdf":"Johnson Angale_FSAmap.pdf","pages":[1,2,3]},
 {"name":"Annette Weekley","roster_county":"Hampton","address":"8225 Pocataligo Rd Hampton SC 29924","workbook_lat":33.5346,"workbook_lon":-80.663,"fields":["4706/11322/2"],"source_pdf":"Annette Weekley_FSA_Map.pdf","pages":[1]},
 {"name":"Albert Vareen","roster_county":"Marion","address":"112 East End Street, Mullins SC 29574","workbook_lat":33.792,"workbook_lon":-79.2745,"fields":["9652/7769/1"],"source_pdf":"Albert vareen_FSA_Map.pdf","pages":[1]},
 {"name":"Rick Boswell","roster_county":"York","address":"1281 Tom Joye Rd Clover SC 29710","workbook_lat":35.0891533,"workbook_lon":-81.2212065,"fields":["4330/8916/1"],"source_pdf":"Rick Boswell.pdf","pages":[1]},
 {"name":"Christopher Riley","roster_county":"Sumter","address":"1095 Armour Hill Drive Pinewood SC 29125","workbook_lat":33.5954525,"workbook_lon":-80.4379171,"fields":["7832/5341/2"],"source_pdf":"Christopher Riley FSAmap1.pdf","pages":[3,4]},
 {"name":"Tyrease Riley","roster_county":"Sumter","address":"1033 Armour Hill Dr Pinewood SC 29125","workbook_lat":33.5946765,"workbook_lon":-80.4385762,"fields":["3603/848/1"],"source_pdf":"Tyreese Riley_FSA Map.pdf","pages":[1]},
 {"name":"Francena Ellis","roster_county":"Jasper","address":"1718 Browning Gate Rd SC 29921","workbook_lat":32.1502,"workbook_lon":-80.7045,"fields":["4083/10683/3","4083/10683/7"],"source_pdf":"Francenia Ellis 2026 FSA Map.pdf","pages":[1]},
]
def get_url(url,params,timeout=17):
 r=requests.get(url,params=params,headers={"User-Agent":"SCSU-farm-boundary-research/1.0 (research GIS)"},timeout=timeout);r.raise_for_status();return r.json()
def geocode(t):
 result=dict(t,geocoder_candidates=[],errors=[])
 def add(service,lat,lon,quality,full_address=""):
  if -83<lon<-78 and 31.5<lat<35.6:
   result["geocoder_candidates"].append(dict(provider=service,lat=float(lat),lon=float(lon),quality=str(quality),matched_address=full_address))
 try:
  d=get_url("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
    dict(address=t["address"],benchmark="Public_AR_Current",vintage="Current_Current",format="json"),25)
  for item in d.get("result",{}).get("addressMatches",[]):
   x=item["coordinates"];add("US_Census",x["y"],x["x"],"MATCHED",item.get("matchedAddress",""))
 except Exception as e:result["errors"].append("Census: "+str(e)[:160])
 try:
  d=get_url("https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
     dict(SingleLine=t["address"],outFields="*",f="json",maxLocations=2),15)
  for item in d.get("candidates",[]):
   add("ArcGIS_geocode",item["location"]["y"],item["location"]["x"],item.get("score",""),item.get("address",""))
 except Exception as e:result["errors"].append("ArcGIS_geocode: "+str(e)[:160])
 try:
  d=get_url("https://geocode-api.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
     dict(SingleLine=t["address"],f="json",maxLocations=2),15)
  for item in d.get("candidates",[]):
   add("ArcGIS_geocode_simple",item["location"]["y"],item["location"]["x"],item.get("score",""),item.get("address",""))
 except Exception as e:result["errors"].append("ArcGIS_simple: "+str(e)[:160])
 try:
  d=get_url("https://nominatim.openstreetmap.org/search",dict(q=t["address"],format="jsonv2",limit=2),18)
  for item in d:add("OSM_Nominatim",float(item["lat"]),float(item["lon"]),item.get("type",""),item.get("display_name",""))
 except Exception as e:result["errors"].append("OSM: "+str(e)[:160])
 # A workbook coordinate is a separate anchor hint, never authoritative.
 add("workbook_coordinate_UNVERIFIED",t["workbook_lat"],t["workbook_lon"],"UNVERIFIED",t["address"])
 # Deduplicate search points with 300-m distance tolerance only when from different providers.
 distinct=[]
 for row in result["geocoder_candidates"]:
  if not any(math.hypot((row["lat"]-q["lat"])*111000,(row["lon"]-q["lon"])*94000)<250 for q in distinct):
   distinct.append(row)
 result["unique_search_anchors"]=distinct[:4]
 return result
with ThreadPoolExecutor(max_workers=7) as pool:results=list(pool.map(geocode,TARGETS))
(OUT/"address_first_anchors.json").write_text(json.dumps(results,indent=2))
for r in results:
 print("ADDRESS",r["name"],"ANCHORS",[(x["provider"],round(x["lat"],6),round(x["lon"],6)) for x in r["unique_search_anchors"]],"ERRORS",r["errors"],flush=True)
