"""Berkeley AMP FSA maps: bounded source-to-aerial registration and county atlas.
Only aerial-registered source outlines enter GeoJSON. Source GPS is a search hint.
"""
import os, json, math, csv, zipfile, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import cv2, numpy as np, fitz, requests
from PIL import Image, ImageStat
from shapely.geometry import Polygon, shape, mapping
from pyproj import Transformer
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from orangeburg_registration_pilot import DETECT, register, strip_result, R

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT=ROOT/'outputs/berkeley_20261106'
OUT.mkdir(parents=True,exist_ok=True)
SIZE=850
SPAN=1650
STEP=850
NAIP='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
ESRI='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'
TO_LL=Transformer.from_crs(3857,4326,always_xy=True)
TO_MERC=Transformer.from_crs(4326,3857,always_xy=True)
COLORS=['#F26058','#1D9A99','#BE8B3B','#744DB5','#347CC7','#A75A8C']
W,H=1224,792

# Pixel traces are deliberately approximate interpretations of source FSA outlines.
# Coordinates are measured on each FSA PDF page rendered at 1.5x.
TARGETS=[
  dict(farm='4198',name='John Loyd',tract='33763',fields={'3':[(287,353),(456,350),(464,624),(368,655)]},
       file='John_Lloyd_FSA_Map.pdf',page=1,county='Berkeley',lon=-79.9344277,lat=33.1877911,crop=(90,160,780,845)),
  dict(farm='4273',name='John Loyd',tract='33795',fields={'5':[(393,444),(460,440),(462,605),(397,601)]},
       file='John_Lloyd_FSA_Map.pdf',page=2,county='Berkeley',lon=-79.9344277,lat=33.1877911,crop=(115,210,750,830)),
  dict(farm='3756',name='John Loyd',tract='3313',fields={'1':[(396,295),(477,283),(446,455),(476,483),(507,674),(469,710),(405,700)]},
       file='John_Lloyd_FSA_Map.pdf',page=3,county='Berkeley',lon=-79.9344277,lat=33.1877911,crop=(150,190,775,780)),
  dict(farm='4236',name='Julian Ramsue',tract='2906',fields={
       '4':[(579,330),(656,348),(635,410),(565,403)],
       '30':[(320,344),(537,397),(532,432),(518,464),(441,475),(385,459),(325,462)]},
       file='Sonya_Ramsue_FSA_Map.pdf',page=2,county='Berkeley',lon=-79.9395655,lat=33.3370337,crop=(10,58,885,920)),
  dict(farm='13739',name='Latonya Flood',tract='45688',fields={
       '2':[(436,252),(502,307),(486,323),(493,392),(498,450),(433,554),(418,688),(401,693),(351,666)]},
       file='Latonya Flood_FSAmap.pdf',page=1,county='Orangeburg',lon=-80.0957283,lat=33.0552013,crop=(10,65,865,925)),
  dict(farm='14118',name='Shane Middleton',tract='46082',fields={
       '23':[(55,487),(111,433),(220,412),(230,470),(141,495)]},
       file='Shane Middleton_FSA Map.pdf',page=1,county='Orangeburg',lon=-80.2426989,lat=33.3706279,crop=(15,70,886,933)),
  dict(farm='9387',name='Shane Middleton',tract='8069',fields={
       '7':[(401,569),(450,539),(475,596),(415,632)],'11':[(360,468),(430,441),(462,484),(405,525)]},
       file='Shane Middleton_FSA Map.pdf',page=2,county='Clarendon',lon=-80.2426989,lat=33.3706279,crop=(15,70,886,933)),
  dict(farm='577',name='Ivan Flood',tract='1397',fields={},
       file='Iven Flood_FSA_Map.pdf',page=1,county='Dorchester',lon=-80.0931768,lat=33.0551942,crop=(35,100,820,915)),
]
def tile_at(lon,lat,dx,dy,provider):
    x,y=TO_MERC.transform(lon,lat); x+=dx*STEP;y+=dy*STEP
    bbox=(x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2)
    url=NAIP if provider=='NAIP' else ESRI
    prm=dict(bbox=','.join(str(v) for v in bbox),bboxSR=3857,imageSR=3857,
             size=f'{SIZE},{SIZE}',format='jpg',f='image')
    try:
        r=requests.get(url,params=prm,timeout=25);r.raise_for_status()
        a=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
        if a is None or a.shape[:2]!=(SIZE,SIZE):return None
        if np.mean(np.std(cv2.resize(a,(32,32)),axis=(0,1)))<5:return None
        return (a,bbox,provider,dx,dy)
    except Exception:return None

def source_views(t):
    f=SOURCE/t['file']
    if not f.exists():return None,[]
    d=fitz.open(f);p=d[t['page']-1]
    pix=p.get_pixmap(matrix=fitz.Matrix(1.5,1.5),alpha=False,colorspace=fitz.csRGB)
    im=cv2.imdecode(np.frombuffer(pix.tobytes('png'),np.uint8),cv2.IMREAD_COLOR)
    h,w=im.shape[:2];out=[]
    for ci,rect in enumerate([t['crop'],None]):
        if rect is None:
            x0,y0,x1,y1=(int(w*.04),int(h*.08),int(w*.96),int(h*.78))
        else:x0,y0,x1,y1=rect
        x0=max(0,min(x0,w-5));x1=min(w,max(x1,x0+5))
        y0=max(0,min(y0,h-5));y1=min(h,max(y1,y0+5))
        crop=im[y0:y1,x0:x1]
        fac=min(1,1000/max(crop.shape[:2]))
        if fac<1:crop=cv2.resize(crop,None,fx=fac,fy=fac)
        gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY)
        kp,desc=DETECT.detectAndCompute(gray,None)
        if desc is None or len(kp)<40:continue
        M=np.array([[fac,0,-fac*x0],[0,fac,-fac*y0],[0,0,1.]],float)
        out.append(((f'c{ci}',crop,kp,desc),M))
    return im,out

def process(t):
    base={k:t[k] for k in ('farm','name','tract','file','page','county')}
    base['roster_county']='Berkeley'
    im,views=source_views(t)
    if im is None:return dict(base,status='FSA_SOURCE_MISSING'),[]
    cv2.imwrite(str(OUT/(t['farm']+'_source.jpg')),im)
    if not views:return dict(base,status='NO_USABLE_IMAGE_FEATURES'),[]
    offsets=[(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1),(2,0),(-2,0),(0,2),(0,-2)]
    tasks=[(pr,dx,dy) for pr in ('NAIP','ESRI') for dx,dy in offsets]
    best=None
    print('REGISTER',t['farm'],'possible_tiles',len(tasks),flush=True)
    with ThreadPoolExecutor(max_workers=8) as pool:
        fs=[pool.submit(tile_at,t['lon'],t['lat'],dx,dy,pr) for pr,dx,dy in tasks]
        for fut in as_completed(fs):
            try:data=fut.result()
            except Exception:data=None
            if data is None:continue
            tile,bbox,provider,dx,dy=data
            for view,M in views:
                try:res=register(view,tile)
                except Exception:continue
                if 'score' not in res:continue
                rank=(bool(res.get('nondegenerate_geographic_match_candidate')),
                      res.get('inliers',0),res['score'])
                if best is None or rank>best[0]:best=(rank,res,view,M,tile,bbox,provider,dx,dy)
    if best is None:return dict(base,status='NO_IMAGE_REGISTRATION_MATCH'),[]
    _,res,view,M,tile,bbox,provider,dx,dy=best
    check=strip_result(res)
    base.update(registration=check,provider=provider,tile_offset=[dx,dy])
    good=bool(res.get('nondegenerate_geographic_match_candidate')) and res.get('inliers',0)>=35 and res.get('rmse_px',99)<3.5
    if not good:return dict(base,status='REGISTRATION_NEEDS_REVIEW'),[]
    Htot=np.asarray(res['H'])@M
    feats=[]
    for field,points in t['fields'].items():
        v=np.float32(points).reshape(-1,1,2)
        try:
            proj=cv2.perspectiveTransform(v,Htot)[:,0,:]
            if not np.isfinite(proj).all():continue
            lon,lat=TO_LL.transform(
                bbox[0]+proj[:,0]/SIZE*(bbox[2]-bbox[0]),
                bbox[3]-proj[:,1]/SIZE*(bbox[3]-bbox[1]))
            poly=Polygon(zip(lon,lat))
            if not poly.is_valid or poly.area<=0:continue
            centroid=poly.representative_point()
            d=math.hypot((centroid.x-t['lon'])*92000,(centroid.y-t['lat'])*111000)
            if d>4000:continue
        except Exception:continue
        feats.append({'type':'Feature','geometry':mapping(poly),
          'properties':{'county':t['county'],'roster_county':'Berkeley',
           'farm_id':t['farm'],'tract_id':t['tract'],'field_id':field,
           'producer':t['name'],'source_file':t['file'],'source_page':t['page'],
           'source_method':'manual rough FSA yellow-outline tracing plus image registration',
           'quality':'APPROXIMATE_DIGITIZED_BOUNDARY_NOT_SURVEY',
           'source_pixel_vertices_1p5x':points,
           'registered_provider':provider,'image_inliers':res['inliers'],
           'registration_rmse_px':res['rmse_px']}})
    cv2.imwrite(str(OUT/(t['farm']+'_match.jpg')),tile)
    base['status']='REGISTERED_APPROXIMATE' if feats else 'ALIGNED_IMAGE__FIELD_BOUNDARY_NOT_EXTRACTED'
    base['fields_georeferenced']=[x['properties']['field_id'] for x in feats]
    print('RESULT',t['farm'],base['status'],len(feats),'matches',res['inliers'],flush=True)
    return base,feats

def census(county):
    fips={'Berkeley':'45015','Clarendon':'45027','Orangeburg':'45075','Dorchester':'45035'}
    u='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
    try:
        r=requests.get(u,params={'where':"GEOID='"+fips[county]+"'",'outFields':'GEOID,NAME','outSR':4326,'f':'geojson'},timeout=25);r.raise_for_status()
        return shape(r.json()['features'][0]['geometry'])
    except Exception:return None

def image_for_bbox(bbox,kind,px=(1600,950)):
    u=ESRI if kind=='Satellite' else 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export'
    parms=dict(bbox=','.join(map(str,bbox)),bboxSR=3857,imageSR=3857,
      size=f'{px[0]},{px[1]}',format='jpg' if kind=='Satellite' else 'png',f='image')
    try:
        r=requests.get(u,params=parms,timeout=40);r.raise_for_status()
        im=Image.open(io.BytesIO(r.content)).convert('RGB')
        if im.size!=px or min(ImageStat.Stat(im.resize((100,100))).stddev)<5:return None
        return im
    except Exception:return None

def extent(geom,pad=.2):
    if geom.geom_type=='MultiPolygon':geom=geom.convex_hull
    xy=np.asarray([TO_MERC.transform(x,y) for x,y in geom.exterior.coords])
    x1,y1=xy.min(axis=0);x2,y2=xy.max(axis=0)
    w=max(300,(x2-x1)*(1+pad*2));h=max(300,(y2-y1)*(1+pad*2))
    aspect=760/490
    if w/h>aspect:h=w/aspect
    else:w=h*aspect
    cx=(x1+x2)/2;cy=(y1+y2)/2
    return (cx-w/2,cy-h/2,cx+w/2,cy+h/2)
def draw_geometry(c,geo,bbox,rect,col,width=2.5):
    x0,y0,ww,hh=rect; x1,y1,x2,y2=bbox
    for polygon in ([geo] if geo.geom_type=='Polygon' else geo.geoms):
        pp=c.beginPath()
        for i,(lon,lat) in enumerate(polygon.exterior.coords):
            x,y=TO_MERC.transform(lon,lat)
            sx=x0+(x-x1)/(x2-x1)*ww;sy=y0+(y-y1)/(y2-y1)*hh
            (pp.moveTo if i==0 else pp.lineTo)(sx,sy)
        pp.close()
        c.setStrokeColor(colors.HexColor(col));c.setLineWidth(width)
        c.drawPath(pp,stroke=1,fill=0)
def image_draw(c,im,rect):
    if im:c.drawImage(ImageReader(im),*rect,mask='auto')
    else:
        c.setFillColor(colors.HexColor('#eff3f5'));c.rect(*rect,fill=1,stroke=0)
        c.setFillColor(colors.HexColor('#a23b34'));c.setFont('Helvetica-Bold',13)
        c.drawString(rect[0]+20,rect[1]+rect[3]/2,'Imagery service unavailable - map not verified')
def header(c,county,kind,sub):
    c.setFillColor(colors.HexColor('#142e47'));c.rect(0,H-18,W,18,fill=1,stroke=0)
    c.setFillColor(colors.HexColor('#142e47'));c.setFont('Helvetica-Bold',13)
    c.drawString(38,753,'SOUTH CAROLINA STATE UNIVERSITY | AMP')
    c.setFont('Helvetica-Bold',26);c.drawString(38,708,county.upper()+' COUNTY')
    c.setFont('Helvetica',12);c.drawString(38,684,kind+'  |  '+sub)
def create_atlas(county,feats,kind):
    boundary=census(county)
    if boundary is None or not feats:return None
    target=OUT/(county+'_County_'+kind+'_FSA_Field_Atlas.pdf')
    c=canvas.Canvas(str(target),pagesize=(W,H))
    allfarms=sorted(set(f['properties']['farm_id'] for f in feats))
    cols={f:COLORS[i%len(COLORS)] for i,f in enumerate(allfarms)}
    # County overview: exact official county outline and indexed field locations.
    header(c,county,kind,'01 / County overview + numbered farm locations')
    co=boundary.simplify(.0007,preserve_topology=True)
    bbox=extent(co,pad=.07);rect=(40,115,825,540)
    im=image_for_bbox(bbox,kind,(1650,1080))
    image_draw(c,im,rect);draw_geometry(c,co,bbox,rect,'#ffffff',4);draw_geometry(c,co,bbox,rect,'#102a42',1.8)
    c.setFillColor(colors.HexColor('#142e47'));c.setFont('Helvetica-Bold',13);c.drawString(910,628,'FARM INDEX')
    for index,farm in enumerate(allfarms,1):
        feature=next(f for f in feats if f['properties']['farm_id']==farm)
        geo=shape(feature['geometry']);p=geo.representative_point();x,y=TO_MERC.transform(p.x,p.y)
        sx=rect[0]+(x-bbox[0])/(bbox[2]-bbox[0])*rect[2];sy=rect[1]+(y-bbox[1])/(bbox[3]-bbox[1])*rect[3]
        c.setFillColor(colors.white);c.circle(sx,sy,11,fill=1,stroke=0)
        c.setFillColor(colors.HexColor(cols[farm]));c.circle(sx,sy,9,fill=1,stroke=0)
        c.setFillColor(colors.white);c.setFont('Helvetica-Bold',9);c.drawCentredString(sx,sy-3,str(index))
        yrow=598-57*(index-1)
        c.setFillColor(colors.HexColor(cols[farm]));c.roundRect(910,yrow-3,24,24,4,fill=1,stroke=0)
        c.setFillColor(colors.white);c.setFont('Helvetica-Bold',11);c.drawCentredString(922,yrow+4,str(index))
        c.setFillColor(colors.HexColor('#142e47'));c.drawString(944,yrow+8,'FARM '+farm)
        c.setFont('Helvetica',10);c.drawString(944,yrow-8,feature['properties']['producer'][:24])
    c.setFont('Helvetica',9);c.setFillColor(colors.HexColor('#455c70'))
    c.drawString(40,75,'Verified imagery registration; approximate FSA-drawn boundaries. Not legal surveys.')
    c.drawString(40,57,'County: U.S. Census TIGERweb | Aerial: Esri World Imagery | Topography: USGS Topo')
    c.showPage()
    for i,f in enumerate(feats,1):
        p=f['properties'];geo=shape(f['geometry']);color=cols[p['farm_id']]
        header(c,county,kind,f"{i+1:02d} / Farm {p['farm_id']} - Field {p['field_id']}")
        bbox=extent(geo,pad=.35);rect=(40,115,825,540)
        im=image_for_bbox(bbox,kind,(1650,1080))
        image_draw(c,im,rect);draw_geometry(c,geo,bbox,rect,'#ffffff',6);draw_geometry(c,geo,bbox,rect,color,3.3)
        c.setFillColor(colors.HexColor('#142e47'));c.setFont('Helvetica-Bold',18);c.drawString(915,624,'FARM '+p['farm_id'])
        c.setFont('Helvetica',13);c.drawString(915,592,p['producer'])
        c.setFont('Helvetica-Bold',12);c.drawString(915,552,'TRACT '+p['tract_id'])
        c.drawString(915,529,'FIELD '+p['field_id'])
        c.setFont('Helvetica',10);c.drawString(915,490,'Source: '+p['source_file'][:35])
        c.drawString(915,469,'FSA outline, approximate')
        c.drawString(915,448,'Image registration: '+p['registered_provider'])
        c.drawString(915,427,'Not a property survey')
        c.setFont('Helvetica',9);c.drawString(40,70,'Source field traced from supplied FSA map; displayed over independent basemap.')
        c.showPage()
    c.save()
    with fitz.open(target) as d:
        if len(d)!=len(feats)+1:raise ValueError('Incorrect atlas page count')
    print('ATLAS',target,len(feats)+1,flush=True)
    return target

def main():
    rows=[];fs=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs=[pool.submit(process,t) for t in TARGETS]
        for fut in as_completed(jobs):
            try:r,features=fut.result()
            except Exception as exc:r={'status':'FAILED','error':str(exc)};features=[]
            rows.append(r);fs.extend(features)
            (OUT/'registration_progress.json').write_text(json.dumps(rows,indent=2))
    fc={'type':'FeatureCollection','features':fs}
    (OUT/'all_registered_fsa_fields.geojson').write_text(json.dumps(fc,indent=2))
    ber=[f for f in fs if f['properties']['county']=='Berkeley']
    (OUT/'Berkeley_registered_fields.geojson').write_text(json.dumps({'type':'FeatureCollection','features':ber},indent=2))
    (OUT/'field_status.json').write_text(json.dumps(rows,indent=2))
    with open(OUT/'field_status.csv','w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=['farm','name','tract','county','roster_county','file','page','status','fields_georeferenced'])
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(row.get(k,'')) if isinstance(row.get(k),list) else row.get(k,'') for k in writer.fieldnames})
    for kind in ('Satellite','Topography'):
        create_atlas('Berkeley',ber,kind)
    with zipfile.ZipFile(OUT/'Berkeley_FSA_Atlas_GeoJSON_Package.zip','w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for file in sorted(OUT.iterdir()):
            if file.name.endswith(('.pdf','.geojson','.csv','.json')):z.write(file,file.name)
    print('COMPLETE',len(ber),'Berkeley field polygons',len(fs),'all counties',flush=True)
if __name__=='__main__':main()
