"""2026-11-09: Publish current AMP field-polygon atlases from curated geometry.
Never use rejected 719-feature synthetic master or historic point-only PDFs.
Each county: county outline and farm markers, then zoomed polygon maps (two styles).
"""
from pathlib import Path
import io, json, csv, math, zipfile, subprocess, os, hashlib, concurrent.futures
from collections import defaultdict
import requests
from PIL import Image, ImageStat
from shapely.geometry import shape
from shapely.ops import unary_union, transform
from pyproj import Transformer
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
import fitz

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'deliverables/current_polygon_atlases_2026-11-09'
OUT.mkdir(parents=True,exist_ok=True)
TMP=ROOT/'outputs/current_atlas_image_cache_2026-11-09'
TMP.mkdir(parents=True,exist_ok=True)
MERC=Transformer.from_crs(4326,3857,always_xy=True)
W,H=1224,792
MAP=(35,103,844,552)
INDEX_X=907
FIPS={'Aiken':'45003','Bamberg':'45009','Barnwell':'45011','Berkeley':'45015',
'Charleston':'45019','Clarendon':'45027','Colleton':'45029','Darlington':'45031',
'Florence':'45041','Greenwood':'45047','Jasper':'45053','Marion':'45067',
'Marlboro':'45069','Orangeburg':'45075','Williamsburg':'45089','York':'45091'}
INPUTS=[
 'geojson/registered_scanned_fields.geojson',
 'geojson/counties/bamberg_corey_3523_fsa_and_john_3524_qgis_area_20261106.geojson',
 'geojson/counties/barnwell_fsa_fields.geojson',
 'geojson/counties/berkeley_4_registered_fields_v5_20261106.geojson',
 'geojson/counties/charleston_registered_selected_field.geojson',
 'geojson/counties/clarendon_selected_fields_7of16_20261106.geojson',
 'geojson/counties/colleton_new_verified_fsa_fields_20261106.geojson',
 'geojson/counties/darlington_selected_5_fields.geojson',
 'geojson/counties/florence_fsa_fields.geojson',
 'geojson/counties/greenwood_myra_louden_and_jasper_john_lee_registered_20261106.geojson',
 'geojson/counties/marion_fsa_fields.geojson',
 'geojson/counties/marlboro_registered_selected_field.geojson',
 'geojson/orangeburg_registered_fields.geojson',
 'geojson/counties/orangeburg_new_verified_fsa_fields_20261106.geojson',
 'geojson/counties/berkeley_roster_14118_orangeburg_field_23_20261106.geojson',
 'geojson/counties/williamsburg_fsa_fields.geojson',
 'geojson/counties/york_registered_selected_field.geojson']
COLOR=['#D34D40','#167C8A','#8A62B8','#B47D22','#4574BC','#A75D84','#5B8453','#C27D51',
       '#6C6D94','#AF525A','#80873B','#3D7F7A','#9D67C1','#AA8539']
SERVICES={
 'Satellite':'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export',
 'Topography':'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export'}
NAIP='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
notes={'Bamberg':'John Brabham polygon is QGIS farm AREA, not separately confirmed FSA Field 25.',
'Berkeley':'Partial 4 selected fields; farm identification discrepancies remain.',
'Charleston':'Only Keesha Jenkins field mapped; Sharon Taylor unresolved.',
'Clarendon':'7 selected fields from Farm IDs 9274 and 1118; 9 Clarendon roster fields remain.',
'Colleton':'Only two mapped fields; other producer maps need geographic registration.',
'Darlington':'5 mapped fields including transferred Marva Jackson and Anthony Jackson.',
'Florence':'Registered field subset only; not complete enrollment coverage.',
'Greenwood':'Myra Louden boundary needs source-area review; not a survey.',
'Jasper':'John Lee fields mapped in Jasper; enrolled under Hampton in AMP workbook.',
'Marion':'Partial; other farm fields remain unresolved.',
'Orangeburg':'12 original mapped fields plus Farm 4261 (Sumter roster) and Farm 14118 (Berkeley roster); remaining maps unresolved.'}
def feats():
 out={}
 for path in INPUTS:
  f=ROOT/path
  if not f.is_file():raise FileNotFoundError(path)
  for item in json.loads(f.read_text())['features']:
   p=item.get('properties',{})
   county=str(p.get('county') or '')
   if county not in FIPS:continue
   geom=shape(item['geometry'])
   if geom.is_empty or not geom.is_valid:continue
   if p.get('geometry_represents')=='USER_QGIS_DIGITIZED_APPROXIMATE_FARM_AREA':
    p['atlas_qualifier']='USER QGIS FARM AREA; not FSA field polygon'
   k=(str(p.get('farm_id') or ''),str(p.get('tract_id') or ''),str(p.get('field_id') or ''))
   out.setdefault(county,{})
   # Preserve first accepted record per county, farm, tract, field; do not merge two different sources.
   out[county].setdefault(k,item)
 return {k:list(v.values()) for k,v in out.items()}

def county_geometry(county):
 u='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
 try:
  r=requests.get(u,params=dict(where=f"GEOID='{FIPS[county]}'",outFields='GEOID,NAME',
      outSR='4326',f='geojson'),timeout=28);r.raise_for_status()
  js=r.json();return shape(js['features'][0]['geometry'])
 except Exception:
  f=ROOT/'geojson/sc_counties_for_verified_atlases.geojson'
  for item in json.loads(f.read_text()).get('features',[]):
   if item['properties'].get('NAME')==county:return shape(item['geometry'])
  raise RuntimeError('Official Census county outline unavailable: '+county)

def bounds_for(geom,pad=.12):
 g=transform(MERC.transform,geom);a,b,c,d=g.bounds
 cx,cy=(a+c)/2,(b+d)/2
 width=max(350,(c-a)*(1+2*pad))
 height=max(220,(d-b)*(1+2*pad))
 aspect=MAP[2]/MAP[3]
 if width/height>aspect:height=width/aspect
 else:width=height*aspect
 return (cx-width/2,cy-height/2,cx+width/2,cy+height/2)

def cached_basemap(county,style,tag,bbox):
 f=TMP/f'{county}_{style}_{tag}.jpg'
 if f.exists():return f
 url=SERVICES[style]
 params={'bbox':','.join(f'{v:.3f}' for v in bbox),'bboxSR':'3857','imageSR':'3857',
         'size':'1600,1045','format':'jpg' if style=='Satellite' else 'png','f':'image'}
 for attempt in range(3):
  endpoint=url if (style=='Topography' or attempt<2) else NAIP
  try:
   resp=requests.get(endpoint,params=params,timeout=45)
   resp.raise_for_status()
   im=Image.open(io.BytesIO(resp.content)).convert('RGB')
   if im.size!=(1600,1045):raise ValueError('wrong image size')
   if min(ImageStat.Stat(im.resize((80,50))).stddev)<3:raise ValueError('blank imagery')
   im.save(f,'JPEG',quality=86,optimize=True)
   return f
  except Exception as exc:
   if attempt==2:raise RuntimeError(f'{county}/{style}/{tag} imagery: {exc}')
 return f

def map_xy(lon,lat,bbox):
 x,y=MERC.transform(lon,lat)
 return (MAP[0]+(x-bbox[0])/(bbox[2]-bbox[0])*MAP[2],
         MAP[1]+(y-bbox[1])/(bbox[3]-bbox[1])*MAP[3])
def stroke_polygon(pdf,geometry,bbox,col='#D34D40',width=2.5):
 from reportlab.pdfbase.pdfmetrics import stringWidth
 g=geometry
 if g.geom_type=='GeometryCollection':geoms=[x for x in g.geoms if x.geom_type in ('Polygon','MultiPolygon')]
 elif g.geom_type=='MultiPolygon':geoms=list(g.geoms)
 else:geoms=[g]
 for poly in geoms:
  if poly.geom_type=='MultiPolygon':
   for pg in poly.geoms:stroke_polygon(pdf,pg,bbox,col,width)
   continue
  ring=poly.exterior.coords
  path=pdf.beginPath()
  for i,(lon,lat) in enumerate(ring):
   x,y=map_xy(lon,lat,bbox)
   (path.moveTo if i==0 else path.lineTo)(x,y)
  path.close()
  pdf.setStrokeColor(colors.HexColor(col));pdf.setLineWidth(width)
  pdf.drawPath(path,stroke=1,fill=0)

def base_page(pdf,county,style,subtitle,basemap):
 pdf.setFillColor(colors.HexColor('#132d45'));pdf.rect(0,H-18,W,18,fill=1,stroke=0)
 pdf.setFillColor(colors.HexColor('#132d45'));pdf.setFont('Helvetica-Bold',13)
 pdf.drawString(35,754,'SOUTH CAROLINA STATE UNIVERSITY  |  AMP PROGRAM')
 pdf.setFont('Helvetica-Bold',27);pdf.drawString(35,714,county.upper()+' COUNTY')
 pdf.setFont('Helvetica',12);pdf.drawString(35,691,style+'  /  '+subtitle)
 pdf.drawImage(ImageReader(str(basemap)),MAP[0],MAP[1],MAP[2],MAP[3],mask='auto')
 pdf.setFillColor(colors.HexColor('#526578'));pdf.setFont('Helvetica',9)
 pdf.drawString(35,75,'Boundaries are approximate FSA-source or QGIS interpretations; NOT legal surveys or USDA CLU exports.')
 pdf.drawString(35,59,'County outline: U.S. Census | Satellite: Esri World Imagery or USGS NAIP | Topography: USGS')
 pdf.setFillColor(colors.HexColor('#122a42'));pdf.setFont('Helvetica-Bold',12)
 pdf.drawCentredString(MAP[0]+MAP[2]-30,MAP[1]+MAP[3]-34,'N')
 pdf.line(MAP[0]+MAP[2]-30,MAP[1]+MAP[3]-58,MAP[0]+MAP[2]-30,MAP[1]+MAP[3]-39)
 pdf.line(MAP[0]+MAP[2]-30,MAP[1]+MAP[3]-39,MAP[0]+MAP[2]-35,MAP[1]+MAP[3]-50)
 pdf.line(MAP[0]+MAP[2]-30,MAP[1]+MAP[3]-39,MAP[0]+MAP[2]-25,MAP[1]+MAP[3]-50)
 pdf.setStrokeColor(colors.white);pdf.setLineWidth(.7);pdf.rect(*MAP,stroke=1,fill=0)
 pdf.setStrokeColor(colors.HexColor('#556878'));pdf.setLineWidth(1.3)
 pdf.line(35,98,879,98)
def draw_index(pdf,farms,items,county):
 pdf.setFillColor(colors.HexColor('#132d45'));pdf.setFont('Helvetica-Bold',14)
 pdf.drawString(INDEX_X,643,'FARM INDEX')
 for idx,(farm,feats) in enumerate(farms.items(),1):
  y=610-38*(idx-1)
  if y<143:break
  col=COLOR[(idx-1)%len(COLOR)]
  pdf.setFillColor(colors.HexColor(col));pdf.roundRect(INDEX_X,y-8,25,24,4,fill=1,stroke=0)
  pdf.setFillColor(colors.white);pdf.setFont('Helvetica-Bold',11);pdf.drawCentredString(INDEX_X+12,y,str(idx))
  pdf.setFillColor(colors.HexColor('#132d45'));pdf.setFont('Helvetica-Bold',11)
  pdf.drawString(INDEX_X+34,y+4,'FARM '+farm)
  prod=str(feats[0]['properties'].get('producer') or '')[:27]
  pdf.setFont('Helvetica',9);pdf.drawString(INDEX_X+34,y-10,prod)
 pdf.setFillColor(colors.HexColor('#506679'));pdf.setFont('Helvetica',9)
 pdf.drawString(INDEX_X,121,f'{len(farms)} mapped farm group(s)')
 note=notes.get(county,'Mapped FSA-field subset; incomplete fields are omitted.')
 for line in [note[i:i+45] for i in range(0,min(180,len(note)),45)]:
  pdf.drawString(INDEX_X,97-(note.index(line)//45)*12,line)
def draw_detail(pdf,feats,bbox,idx,county):
 for f in feats:
  p=f['properties'];col=COLOR[(idx-1)%len(COLOR)]
  stroke_polygon(pdf,shape(f['geometry']),bbox,'#ffffff',5)
  stroke_polygon(pdf,shape(f['geometry']),bbox,col,2.8)
  rep=shape(f['geometry']).representative_point();x,y=map_xy(rep.x,rep.y,bbox)
  pdf.setFillColor(colors.white);pdf.roundRect(x-10,y-9,20,17,3,fill=1,stroke=0)
  pdf.setFillColor(colors.HexColor('#173047'));pdf.setFont('Helvetica-Bold',9)
  pdf.drawCentredString(x,y-4,str(p.get('field_id') or 'A'))
 pdf.setFillColor(colors.HexColor('#132d45'));pdf.setFont('Helvetica-Bold',17)
 p=feats[0]['properties'];farm=str(p.get('farm_id','?'));pdf.drawString(INDEX_X,632,'FARM '+farm)
 pdf.setFont('Helvetica',12);pdf.drawString(INDEX_X,606,str(p.get('producer') or '')[:30])
 y=568
 for f in feats[:11]:
  p=f['properties']
  tract=str(p.get('tract_id') or '?');fld=str(p.get('field_id') or 'farm area')
  pdf.setFont('Helvetica-Bold',10);pdf.drawString(INDEX_X,y,f'Tract {tract}  -  Field {fld}')
  y-=24
 pdf.setFont('Helvetica',9)
 text=notes.get(county,'Approximate FSA field interpretations. Not legal surveys.')
 for i in range(0,len(text),42):
  pdf.drawString(INDEX_X,173-i//42*13,text[i:i+42])
def farm_groups(features):
 d=defaultdict(list)
 for f in features:d[str(f['properties'].get('farm_id') or 'UNKNOWN')].append(f)
 return dict(sorted(d.items(),key=lambda kv:kv[0]))
def tasks_for(county,features,boundary):
 farms=farm_groups(features)
 results=[]
 overview=bounds_for(boundary,.045)
 results.append(('county',overview))
 for idx,(farm,feats) in enumerate(farms.items(),1):
  u=unary_union([shape(x['geometry']) for x in feats])
  results.append((f'farm{farm}',bounds_for(u,.34)))
 return farms,results
def generate(county,features,boundary,style,farms,tasks):
 outdir=OUT/county;outdir.mkdir(parents=True,exist_ok=True)
 name=f'{county}_County_{style}_FSA_Polygon_Atlas.pdf'
 temp=outdir/('_uncompressed_'+name)
 pdf=canvas.Canvas(str(temp),pagesize=(W,H),pageCompression=1)
 bbox=tasks[0][1]
 base_page(pdf,county,style,'County overview and numbered mapped farm locations',cached_basemap(county,style,'county',bbox))
 stroke_polygon(pdf,boundary.simplify(.001,preserve_topology=True),bbox,'#ffffff',4.8)
 stroke_polygon(pdf,boundary.simplify(.001,preserve_topology=True),bbox,'#193955',2.4)
 for idx,(farm,ff) in enumerate(farms.items(),1):
  u=unary_union([shape(x['geometry']) for x in ff]);p=u.representative_point();x,y=map_xy(p.x,p.y,bbox)
  pdf.setFillColor(colors.white);pdf.circle(x,y,11,stroke=0,fill=1)
  pdf.setFillColor(colors.HexColor(COLOR[(idx-1)%len(COLOR)]));pdf.circle(x,y,9,stroke=0,fill=1)
  pdf.setFillColor(colors.white);pdf.setFont('Helvetica-Bold',10);pdf.drawCentredString(x,y-3,str(idx))
 draw_index(pdf,farms,features,county);pdf.showPage()
 for idx,(farm,ff) in enumerate(farms.items(),1):
  bbox=tasks[idx][1]
  base_page(pdf,county,style,f'{idx+1:02d} / Farm {farm} field polygons',cached_basemap(county,style,f'farm{farm}',bbox))
  draw_detail(pdf,ff,bbox,idx,county);pdf.showPage()
 pdf.save()
 final=outdir/name
 cmd=['gs','-q','-dNOPAUSE','-dBATCH','-sDEVICE=pdfwrite','-dCompatibilityLevel=1.6',
      '-dPDFSETTINGS=/ebook','-dDetectDuplicateImages=true','-sOutputFile='+str(final),str(temp)]
 subprocess.run(cmd,check=True,timeout=150)
 temp.unlink()
 with fitz.open(final) as d:
  if len(d)!=len(farms)+1:raise RuntimeError('Invalid page count '+str(final))
 print('PUBLISHED',county,style,len(farms)+1,'pages',final.stat().st_size,flush=True)
 return {'county':county,'map_style':style,'farm_groups':len(farms),'field_features':len(features),
 'pdf':str(final.relative_to(OUT)),'pages':len(farms)+1,'sha256':hashlib.sha256(final.read_bytes()).hexdigest(),
 'coverage_note':notes.get(county,'Mapped FSA field subset; other fields may remain unresolved.')}
def main():
 src=feats()
 if len(src)<16:raise RuntimeError(f'Expected 16 counties, got {list(src)}')
 geom={}
 jobs={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  for county,features in src.items():
   boundary=county_geometry(county);geom[county]=boundary
   farms,tasks=tasks_for(county,features,boundary)
   jobs[county]=(farms,tasks)
   for tag,bbox in tasks:
    for style in SERVICES:
     pool.submit(cached_basemap,county,style,tag,bbox)
  # No further work until all images loaded. Missing basemaps fail explicitly below.
  results=[]
  for county in sorted(src):
   features=src[county];boundary=geom[county];farms,tasks=jobs[county]
   for style in ('Satellite','Topography'):
    results.append(generate(county,features,boundary,style,farms,tasks))
 with (OUT/'County_Atlas_Index.csv').open('w',newline='') as stream:
  w=csv.DictWriter(stream,fieldnames=list(results[0].keys()));w.writeheader();w.writerows(results)
 (OUT/'README_START_HERE.txt').write_text('SCSU AMP 2026-11-09 | Polygon-based county atlases\n'
  'One Satellite PDF and one Topography PDF per county. County overview first, then zoomed farm polygon pages.\n'
  'All mapped polygons are approximate and not authoritative FSA CLU or cadastral surveys.\n'
  'Incomplete farm and field coverage is not silently presented as complete.\n'
  'This is a fresh GitHub atlas render from curated FSA/QGIS GeoJSON files; it may differ visually from prior approved PDF layouts.\n'
  'The rejected 719-feature synthetic master is NOT USED. Farmer data: share only with authorized collaborators.\n')
 zipname=ROOT/'outputs/SC_AMP_County_Polygon_Atlases_GitHub_2026-11-09.zip'
 with zipfile.ZipFile(zipname,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
  for f in sorted(OUT.rglob('*')):
   if f.is_file():z.write(f,f.relative_to(OUT))
 print('COMPLETE',len(src),'counties',len(results),'PDFs',zipname.stat().st_size,'ZIP bytes',flush=True)
if __name__=='__main__':main()
