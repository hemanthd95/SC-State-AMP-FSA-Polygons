"""Satellite/topographic county atlases for three image-registered FSA fields.

Uses actual FSA vector edges or hand traces of the printed FSA field outline.
Does not geolocate an unresolved field based on a reported address alone.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
import csv
import json
import math
import zipfile

import cv2
import fitz
import numpy as np
import requests
from PIL import Image, ImageStat
from pyproj import Geod, Transformer
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon, mapping, shape

from build_verified_atlases import fixed_bbox, draw_shape, coord_box, bar_and_north, rings

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source_recovered/unpacked/SC State_AMP_FSA MAP'
OUT=ROOT/'delivery/three_county_20261106'
GEO=ROOT/'geojson/counties'
FIND=ROOT/'analysis/three_county_20261106/results.json'
OUT.mkdir(parents=True,exist_ok=True)
GEO.mkdir(parents=True,exist_ok=True)
GEOD=Geod(ellps='WGS84')
TO_LL=Transformer.from_crs(3857,4326,always_xy=True)
TO_MERC=Transformer.from_crs(4326,3857,always_xy=True)
W,H=1224,792
NAVY=colors.HexColor('#132D46')
MUTED=colors.HexColor('#61748A')
PANEL=colors.HexColor('#F0F4F7')
CYAN=colors.HexColor('#00A8A8')
GOLD=colors.HexColor('#E9A634')
PINK=colors.HexColor('#E95E68')
PALETTE={'Marlboro':CYAN,'York':GOLD,'Charleston':PINK}
FIPS={'Marlboro':'45069','York':'45091','Charleston':'45019'}
BOUNDARY_SOURCE=GEO.parent/'three_county_census_boundaries.geojson'

YORK_SCREEN=[(403,108),(610,196),(613,223),(46,636),(30,500)]
JENKINS_SCREEN=[(175,231),(260,225),(666,655),(626,699)]


def pixels_to_ll(page_vertices, rec):
    pts=np.array([[x,y,1] for x,y in page_vertices],dtype=float)
    h=np.asarray(rec['source_render_to_tile_homography'],dtype=float)
    matched=pts@h.T
    matched=matched[:,:2]/matched[:,2,None]
    minx,miny,maxx,maxy=rec['tile_bbox_epsg3857']
    size=rec['tile_size_wh'][0]
    xs=minx+matched[:,0]/size*(maxx-minx)
    ys=maxy-matched[:,1]/size*(maxy-miny)
    lon,lat=TO_LL.transform(xs,ys)
    return Polygon(zip(lon,lat))


def trace_feature(rec):
    county=rec['county'];farm=rec['farm_id']
    if county=='Marlboro':
        page=fitz.open(SRC/rec['source_pdf'])[0]
        drawing=page.get_drawings()[6]
        coords=[(item[1].x,item[1].y) for item in drawing['items'] if item[0]=='l']
        method='FSA PDF vector boundary, aligned to aerial imagery'
        fid='21';fsa=5.03;producer='Johnie Thomas';tract='10195'
    elif county=='York':
        coords=[(x*1812/825,y*2415/1100) for x,y in YORK_SCREEN]
        method='Hand-traced FSA raster boundary, aligned to aerial imagery'
        fid='1';fsa=None;producer='Rick Boswell';tract='8916'
    elif county=='Charleston':
        coords=[(x*612/849,y*792/1100) for x,y in JENKINS_SCREEN]
        method='Hand-traced FSA raster boundary, aligned to aerial imagery'
        fid='1';fsa=2.23;producer='Keesha Jenkins';tract='1859'
    else:raise ValueError(county)
    geom=pixels_to_ll(coords,rec)
    assert geom.is_valid and geom.area>0,(county,geom.wkt)
    acres=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
    if fsa and abs(acres/fsa-1)>.04:
        raise ValueError(f'{county} FSA area mismatch: {acres:.2f} vs {fsa}')
    props={'county':county,'farm_id':farm,'tract_id':tract,'field_id':fid,
           'producer':producer,'fsa_reported_acres':fsa,'mapped_acres_approx':round(acres,2),
           'source_pdf':rec['source_pdf'],'source_page':rec['source_page'],
           'method':method,'registered_to':rec['tile_provider'],
           'registration_inliers':rec['registration']['inliers'],
           'registration_rmse_pixels':rec['registration']['rmse_px'],
           'status':'FSA_FIELD_OUTLINE_REGISTERED_APPROXIMATE_NOT_SURVEY',
           'source_warning':'Raster-traced boundaries are illustrative; not surveyed',
           'digitization_date':'2026-11-06'}
    return {'type':'Feature','properties':props,'geometry':mapping(geom)}


def img_export(bbox,size,variant):
    endpoint=('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'
        if variant=='Satellite' else
        'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export')
    p={'bbox':','.join(f'{v:.5f}' for v in bbox),'bboxSR':3857,'imageSR':3857,
       'size':f'{size[0]},{size[1]}','format':'jpg' if variant=='Satellite' else 'png',
       'f':'image','transparent':'false'}
    r=requests.get(endpoint,params=p,timeout=35)
    r.raise_for_status()
    im=Image.open(BytesIO(r.content)).convert('RGB')
    if im.size!=size:raise ValueError(f'{variant}: wrong image dimensions {im.size}')
    if max(ImageStat.Stat(im.resize((64,64))).stddev)<7:
        raise ValueError(f'{variant} basemap is blank')
    return im


def label(c,x,y,t,size=10,bold=False,col=NAVY):
    c.setFont('Helvetica-Bold' if bold else 'Helvetica',size)
    c.setFillColor(col)
    c.drawString(x,y,str(t))


def wrap(c,t,x,y,width,size=10,lead=15,col=MUTED):
    for line in simpleSplit(t,'Helvetica',size,width):
        label(c,x,y,line,size,col=col);y-=lead
    return y


def load_county_boundaries():
    """Official U.S. Census TIGERweb polygon geometry, cached for repeat builds."""
    if BOUNDARY_SOURCE.exists():
        collection=json.loads(BOUNDARY_SOURCE.read_text())
    else:
        url='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
        q={
            'where':"GEOID IN ('45019','45069','45091')",
            'outFields':'GEOID,NAME','outSR':'4326','f':'geojson',
        }
        response=requests.get(url,params=q,timeout=35)
        response.raise_for_status()
        collection=response.json()
        if len(collection.get('features',[]))!=3:
            raise ValueError('County boundary source did not return all three counties')
        BOUNDARY_SOURCE.write_text(json.dumps(collection,indent=2)+'\n')
    candidates={str(f['properties']['GEOID']):shape(f['geometry']) for f in collection['features']}
    if set(FIPS.values())-set(candidates):
        raise ValueError('County boundary source missing a requested FIPS ID')
    result={}
    for county,fips in FIPS.items():
        geom=candidates[fips]
        assert geom.is_valid and geom.area>0,(county,geom.is_valid)
        result[county]=geom.simplify(.0007,preserve_topology=True)
    return result


def draw_overview(c,county,feature,boundary,variant,status_rows):
    p=feature['properties'];g=shape(feature['geometry'])
    frame=(42,105,850,558)
    pts=[(lon,lat) for ring in rings(boundary) for lon,lat in ring]
    bounds=fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.10)
    img=img_export(bounds,(1700,1116),variant)
    color=PALETTE[county]
    c.setFillColor(colors.white);c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(NAVY);c.rect(0,H-17,W,17,fill=1,stroke=0)
    label(c,42,750,'SOUTH CAROLINA STATE UNIVERSITY   /   AMP PROGRAM',11,True)
    label(c,42,707,f'{county.upper()} COUNTY',27,True)
    label(c,42,684,f'{variant} field atlas   /   01 - County overview and farm locations',12,col=MUTED)
    c.setFillColor(PANEL);c.rect(0,0,W,78,fill=1,stroke=0)
    c.drawImage(ImageReader(img),*frame,mask='auto')
    c.setStrokeColor(colors.HexColor('#B8CAD7'));c.setLineWidth(1.1);c.rect(*frame,fill=0,stroke=1)
    ll2px=coord_box(bounds,frame)
    draw_shape(c,boundary,ll2px,colors.white,width=4.5)
    draw_shape(c,boundary,ll2px,NAVY,width=2.0)
    marker=g.representative_point()
    x,y=ll2px(marker.x,marker.y)
    # White halo keeps the indexed FSA field location visible on any basemap.
    c.setFillColor(colors.white);c.circle(x,y,16,fill=1,stroke=0)
    c.setFillColor(color);c.circle(x,y,13,fill=1,stroke=0)
    c.setFillColor(colors.white);c.setFont('Helvetica-Bold',11)
    c.drawCentredString(x,y-3.8,'1')
    bar_and_north(c,bounds,frame)
    label(c,925,621,'FARM LOCATION INDEX',12,True)
    c.setFillColor(color);c.roundRect(925,580,27,27,5,fill=1,stroke=0)
    c.setFillColor(colors.white);c.setFont('Helvetica-Bold',12);c.drawCentredString(938.5,587,'1')
    label(c,963,590,f'FARM {p["farm_id"]}',15,True)
    label(c,925,556,p['producer'],13,True)
    label(c,925,531,f'Tract {p["tract_id"]}  /  Field {p["field_id"]}',11,col=MUTED)
    y=492
    y=wrap(c,'Numbered marker shows the FSA field location inside the county boundary.',925,y,250,10,15)-17
    n_total=sum(r['county']==county for r in status_rows)
    label(c,925,y,f'{1} of {n_total} roster farm(s) mapped',11,True);y-=34
    if n_total>1:
        label(c,925,y,'PENDING FIELD PLACEMENT',10,True,col=PINK);y-=20
        for row in status_rows:
            if row['county']==county and row['status']!='MAPPED':
                y=wrap(c,f'{row["producer"]} (Farm {row["farm_id"]}) - source map present; no verified polygon.',925,y,250,10,15)-12
    y=max(y-18,175)
    label(c,925,y,'NEXT PAGE',11,True)
    wrap(c,'Close-up aerial/topographic map with the traced field polygon highlighted in its Farm ID color.',925,y-22,250,10,15)
    label(c,42,50,'PRIVATE   |   County outline: U.S. Census TIGERweb   |   Map: '+('Esri World Imagery' if variant=='Satellite' else 'USGS US Topo'),9,col=MUTED)
    label(c,42,32,'Field location is derived from the georeferenced FSA outline, not the producer address.   |   PAGE 1 OF 2',9,col=MUTED)
    c.showPage()


def build_pdf(county, feature, variant, status_rows, county_boundary):
    p=feature['properties'];geom=shape(feature['geometry']);color=PALETTE[county]
    frame=(42,105,850,558)
    projected=[TO_MERC.transform(x,y) for x,y in geom.exterior.coords]
    lonlat=list(geom.exterior.coords)
    bounds=fixed_bbox(lonlat,frame[2]/frame[3],pad_fraction=.32,min_m=300)
    img=img_export(bounds,(1700,1116),variant)
    target=OUT/f'{county}_County_{variant}_Field_Polygons.pdf'
    c=canvas.Canvas(str(target),pagesize=(W,H),pageCompression=1)
    c.setTitle(f'{county} County | FSA Field Atlas | {variant}')
    draw_overview(c,county,feature,county_boundary,variant,status_rows)
    c.setFillColor(colors.white);c.rect(0,0,W,H,fill=1,stroke=0)
    c.setFillColor(NAVY);c.rect(0,H-17,W,17,fill=1,stroke=0)
    label(c,42,750,'SOUTH CAROLINA STATE UNIVERSITY   /   AMP PROGRAM',11,True)
    label(c,42,707,f'{county.upper()} COUNTY',27,True)
    label(c,42,684,f'{variant} field atlas   /   02 - FSA-derived field boundary',12,col=MUTED)
    c.setFillColor(PANEL);c.rect(0,0,W,78,fill=1,stroke=0)
    c.drawImage(ImageReader(img),*frame,mask='auto')
    c.setStrokeColor(colors.HexColor('#B8CAD7'));c.setLineWidth(1.1);c.rect(*frame,fill=0,stroke=1)
    ll2px=coord_box(bounds,frame)
    draw_shape(c,geom,ll2px,colors.white,width=5.5)
    draw_shape(c,geom,ll2px,color,width=3.4,fillalpha=.22)
    point=geom.representative_point();x,y=ll2px(point.x,point.y)
    c.setFillColor(NAVY);c.roundRect(x-39,y-13,78,26,6,fill=1,stroke=0)
    c.setFillColor(colors.white);c.setFont('Helvetica-Bold',11)
    c.drawCentredString(x,y-3,f'FIELD {p["field_id"]}')
    bar_and_north(c,bounds,frame)
    c.setFillColor(color);c.roundRect(925,609,25,25,5,fill=1,stroke=0)
    label(c,958,616,f'FARM {p["farm_id"]}',18,True)
    label(c,925,587,p['producer'],13,True)
    label(c,925,553,f'TRACT {p["tract_id"]}   /   FIELD {p["field_id"]}',11,col=MUTED)
    c.setStrokeColor(colors.HexColor('#D6E0E7'));c.line(925,535,1183,535)
    label(c,925,502,'SOURCE & PLACEMENT',11,True)
    y=477
    for line in ['USDA FSA map outline',f'{p["registration_inliers"]} matching aerial features',
                 f'Image residual: {p["registration_rmse_pixels"]:.2f} px']:
        label(c,925,y,line,10,col=MUTED);y-=22
    y-=12
    if p['fsa_reported_acres']:
        label(c,925,y,f'FSA label: {p["fsa_reported_acres"]:g} ac',11,True);y-=23
    label(c,925,y,f'Illustrated: ~{p["mapped_acres_approx"]:.1f} ac',10,col=MUTED);y-=35
    y=wrap(c,'Source imagery is geographically aligned to the present basemap. Boundary is approximate and is not a survey.',925,y,250,10,15)
    others=[r for r in status_rows if r['county']==county and r['status']!='MAPPED']
    if others:
        y-=31
        label(c,925,y,'REQUIRES REVIEW',11,True,col=PINK);y-=22
        for row in others:
            y=wrap(c,f'{row["producer"]} (Farm {row["farm_id"]}): FSA map present; field location not yet verified.',925,y,250,10,15)-12
    label(c,42,50,'PRIVATE   |   Sources: USDA FSA producer map and '+('Esri World Imagery' if variant=='Satellite' else 'USGS US Topo'),9,col=MUTED)
    label(c,42,32,'WGS84 GeoJSON / Web Mercator map. Boundaries illustrative, not legal surveys.   |   PAGE 2 OF 2',9,col=MUTED)
    c.showPage();c.save()
    return target


def main():
    rows=json.loads(FIND.read_text())
    supported=[r for r in rows if r['status']=='POTENTIAL_REGISTRATION_NEEDS_FIELD_TRACE']
    assert {r['county'] for r in supported}=={'Marlboro','York','Charleston'}
    # Reuse the accepted first-batch GeoJSONs; PDF layout corrections must not
    # silently alter the same field boundaries or trigger new registration.
    features={}
    for rec in supported:
        path=GEO/f'{rec["county"].lower()}_registered_selected_field.geojson'
        if path.exists():
            feature=json.loads(path.read_text())['features'][0]
            assert str(feature['properties']['farm_id'])==str(rec['farm_id'])
            features[rec['county']]=feature
        else:
            features[rec['county']]=trace_feature(rec)
    boundaries=load_county_boundaries()
    status=[]
    for rec in rows:
        county=rec['county'];fid=rec['farm_id']
        names={'3776':'Johnie Thomas','4330':'Rick Boswell','1436':'Keesha Jenkins','1134':'Sharon Taylor'}
        status.append({'county':county,'farm_id':fid,'producer':names[fid],
                       'status':'MAPPED' if county in features and features[county]['properties']['farm_id']==fid else 'FSA_PRESENT_GEOGRAPHIC_ALIGNMENT_UNRESOLVED',
                       'source_pdf':rec['source_pdf'],
                       'detail':rec['status']})
    outputs=[]
    for county,feature in features.items():
        target=GEO/f'{county.lower()}_registered_selected_field.geojson'
        if not target.exists():
            target.write_text(json.dumps({'type':'FeatureCollection','features':[feature]},indent=2)+'\n')
        outputs.append(target)
    outputs.append(BOUNDARY_SOURCE)
    with (OUT/'Three_County_Field_Status.csv').open('w',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=list(status[0]));writer.writeheader();writer.writerows(status)
    outputs.append(OUT/'Three_County_Field_Status.csv')
    jobs=[(county,f,variant) for county,f in features.items() for variant in ('Satellite','Topography')]
    with ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(build_pdf,county,f,variant,status,boundaries[county]) for county,f,variant in jobs]
        for fut in as_completed(tasks):
            pdf=fut.result();outputs.append(pdf);print('PDF',pdf.name,pdf.stat().st_size,flush=True)
    zipfile_path=OUT/'Three_County_FSA_Field_Atlases_GeoJSON.zip'
    with zipfile.ZipFile(zipfile_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in sorted(outputs):
            z.write(path,path.name)
    print('FINISHED',zipfile_path,'bytes',zipfile_path.stat().st_size,'mapped',len(features),'unresolved',len(status)-len(features),flush=True)


if __name__=='__main__':main()
