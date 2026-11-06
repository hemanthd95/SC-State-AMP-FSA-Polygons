"""Fetch official Clarendon county outline and real map backgrounds; coordinates are approximate field centroids."""
from pathlib import Path
import json, math, io, requests
from PIL import Image,ImageStat
from shapely.geometry import shape
from pyproj import Transformer
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/clarendon_backgrounds_20261106'
OUT.mkdir(parents=True,exist_ok=True)
county_url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
r=requests.get(county_url,params=dict(where="GEOID='45027'",outFields='GEOID,NAME',outSR='4326',f='geojson'),timeout=50)
r.raise_for_status()
data=r.json()
if not data.get('features'):raise RuntimeError('No official Clarendon boundary')
(OUT/'Clarendon_County_Boundary.geojson').write_text(json.dumps(data,indent=2))
poly=shape(data['features'][0]['geometry'])
project=Transformer.from_crs(4326,3857,always_xy=True)
# bbox from county coordinates
from shapely.ops import transform
m=transform(project.transform,poly)
minx,miny,maxx,maxy=m.bounds
cx,cy=(minx+maxx)/2,(miny+maxy)/2
scale=max((maxx-minx)*1.17/1.68,(maxy-miny)*1.18)
areas=[dict(name='county',bbox=[cx-scale*1.68/2,cy-scale/2,cx+scale*1.68/2,cy+scale/2])]
for name,lon,lat,width in [
 ('farm_9274_tract_646',-80.3554,33.6713,850),
 ('farm_9274_tract_662',-80.3562,33.6748,720),
 ('farm_1118_tract_2455',-80.2922,33.6460,850),
 ('farm_1118_tract_4102',-80.2932,33.6468,800)]:
 x,y=project.transform(lon,lat); h=width/1.68
 areas.append(dict(name=name,bbox=[x-width/2,y-h/2,x+width/2,y+h/2]))
services={
 'satellite':'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export',
 'topography':'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export'}
metadata=[]
for target in areas:
 for kind,url in services.items():
  bb=target['bbox']; fmat='jpg' if kind=='satellite' else 'png'
  params=dict(bbox=','.join(f'{v:.4f}' for v in bb),bboxSR=3857,imageSR=3857,size='1680,1000',format=fmat,f='image',dpi=140)
  try:
   r=requests.get(url,params=params,timeout=65);r.raise_for_status()
   im=Image.open(io.BytesIO(r.content)).convert('RGB')
   if im.size!=(1680,1000) or min(ImageStat.Stat(im.resize((96,64))).stddev)<4:
    raise ValueError('blank basemap')
   filename=f'{target["name"]}_{kind}.jpg'
   im.save(OUT/filename,'JPEG',quality=92,optimize=True)
   metadata.append(dict(name=target['name'],type=kind,status='OK',file=filename,bbox=bb,image_size=[1680,1000]))
   print('READY',filename,(OUT/filename).stat().st_size,flush=True)
  except Exception as exc:
   metadata.append(dict(name=target['name'],type=kind,status='MISSING',error=str(exc),bbox=bb))
   print('FAILED',target['name'],kind,str(exc),flush=True)
(OUT/'basemaps_manifest.json').write_text(json.dumps(metadata,indent=2))
print('DONE',sum(r['status']=='OK' for r in metadata),'of',len(metadata),flush=True)
