"""Build GIS-registered county atlases for FSA GeoPDF fields only.

Source PDF coordinates are reproduced from PDF viewport reference points and
vector path vertices. No unverified spreadsheet/address location is used.
"""
from collections import defaultdict
from io import BytesIO
from pathlib import Path
import csv
import hashlib
import json
import math
import re
import time
import zipfile

import fitz
from PIL import Image, ImageStat
from pyproj import Geod, Transformer
from shapely.geometry import shape, Polygon, mapping
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
import requests

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUTPUT = ROOT / 'verified_atlas_deliverables'
W, H = 1224, 792
NAVY = colors.HexColor('#133047')
INK = colors.HexColor('#233745')
PALE = colors.HexColor('#EEF4F6')
GRAY = colors.HexColor('#637781')
GOLD = colors.HexColor('#F2B044')
PALETTE = ['#F25F4C', '#0795B5', '#B25AC4', '#72A251', '#EA9A31', '#4263C6', '#B06D43', '#CE4477', '#388F79', '#A39426', '#704FB7', '#307A9D', '#B85724', '#5C8759', '#9B507E', '#B17535', '#3973AD', '#7E9C4D']
COUNTIES = {'Aiken':'45003', 'Allendale':'45005', 'Barnwell': '45011', 'Darlington': '45031', 'Florence': '45041', 'Marion': '45067', 'Williamsburg': '45089'}
GEOD = Geod(ellps='WGS84')
TO_UTM = Transformer.from_crs(4326, 32617, always_xy=True)
FROM_UTM = Transformer.from_crs(32617, 4326, always_xy=True)
TO_MERC = Transformer.from_crs(4326, 3857, always_xy=True)
FROM_MERC = Transformer.from_crs(3857, 4326, always_xy=True)
cache = {}


def nums(v):
    return list(map(float, re.findall(r'[-+]?(?:\d*\.\d+|\d+)', v)))


def registered_vector(doc, page, index):
    vp = doc.xref_get_key(page.xref, 'VP')[1]
    bbox = nums(re.search(r'/BBox\s*\[([^]]+)\]', vp).group(1))
    measure = int(re.search(r'/Measure\s+(\d+)\s+0\s+R', vp).group(1))
    import numpy as np
    lpts = np.array(nums(doc.xref_get_key(measure, 'LPTS')[1])).reshape(-1, 2)
    gpts = np.array(nums(doc.xref_get_key(measure, 'GPTS')[1])).reshape(-1, 2)
    east, north = TO_UTM.transform(gpts[:, 1], gpts[:, 0])
    affine, *_ = np.linalg.lstsq(np.column_stack([lpts, np.ones(len(lpts))]),
                                  np.column_stack([east, north]), rcond=None)
    drawing = page.get_drawings()[index]
    vertices = []
    for item in drawing['items']:
        if item[0] != 'l':
            raise ValueError('Cannot reproduce non-straight FSA boundary segment')
        if not vertices:
            vertices.append(tuple(item[1]))
        vertices.append(tuple(item[2]))
    if vertices[-1] != vertices[0]:
        vertices.append(vertices[0])
    xy = np.array(vertices)
    loc = np.column_stack([(xy[:, 0] - bbox[0])/(bbox[2]-bbox[0]),
                           (page.rect.height - xy[:, 1] - bbox[1])/(bbox[3]-bbox[1]),
                           np.ones(len(xy))])
    e_n = loc @ affine
    lon, lat = FROM_UTM.transform(e_n[:, 0], e_n[:, 1])
    geom = Polygon(np.column_stack([lon, lat]))
    if not geom.is_valid or geom.area <= 0:
        raise ValueError('Invalid registered polygon')
    return geom


def fetch_image(bounds, width, height, kind):
    key = (tuple(round(x, 7) for x in bounds), width, height, kind)
    if key in cache:
        return cache[key]
    bbox = ','.join(f'{v:.9f}' for v in bounds)
    services = ([
        ('USGS NAIP', 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage', 'jpg', True),
        ('Esri World Imagery', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export', 'jpg', False),
    ] if kind == 'Satellite' else [
        ('USGS US Topo', 'https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export', 'png', False),
        ('Esri World Topographic Map', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/export', 'png', False),
    ])
    for label, url, fmt, is_imgserver in services:
        for attempt in range(4):
            # Native USGS ImageServer expands angular EPSG:4326 extents to
            # match raster aspect ratio, shifting mapped FSA polygons by up
            # to 20%. Use conformal Web Mercator at an *exact* pixel ratio.
            params = {'bbox': bbox, 'bboxSR': 3857, 'imageSR': 3857,
                      'size': f'{width},{height}', 'format': fmt, 'f': 'image',
                      'transparent': 'false'}
            if is_imgserver:
                params['interpolation'] = '+RSP_BilinearInterpolation'
            try:
                r = requests.get(url, params=params, timeout=55)
                r.raise_for_status()
                img = Image.open(BytesIO(r.content)).convert('RGB')
                if img.size != (width, height):
                    raise ValueError(f'Wrong imagery size: {img.size}')
                std = ImageStat.Stat(img.resize((64, 64))).stddev
                if max(std) < 8:
                    raise ValueError('Basemap appears blank')
                if label == 'USGS NAIP':
                    sample = img.resize((100, 100))
                    black = sum(1 for red, green, blue in sample.getdata()
                                if red < 4 and green < 4 and blue < 4)
                    if black > 100:
                        raise ValueError(f'USGS NAIP has {black/100:.1f}% black missing-image area')
                cache[key] = (img, label)
                return img, label
            except Exception as e:
                if attempt == 3:
                    print('IMAGE_PROVIDER_FAILED', label, kind, str(e)[:110], flush=True)
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'No real {kind} basemap available for {bounds}')


def font(c, x, y, s, size=10, color=INK, bold=False):
    c.setFillColor(color)
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    c.drawString(x, y, str(s))


def wrap(c, content, x, y, maxwidth, size=10, leading=14, color=INK):
    for logical in str(content).split('\n'):
        for line in simpleSplit(logical, 'Helvetica', size, maxwidth) or ['']:
            font(c, x, y, line, size, color)
            y -= leading
    return y


def common(c, county, base, title, page_num, source_label):
    c.setFillColor(NAVY)
    c.rect(0, H-15, W, 15, stroke=0, fill=1)
    font(c, 40, 753, 'SOUTH CAROLINA STATE UNIVERSITY   /   AMP PROGRAM', 11, NAVY, True)
    font(c, 40, 719, f'{county} County', 26, NAVY, True)
    font(c, 40, 691, title, 12, GRAY)
    c.setStrokeColor(colors.HexColor('#D6E0E4'))
    c.line(40, 674, 1184, 674)
    c.setFillColor(PALE)
    c.rect(0, 0, W, 65, fill=1, stroke=0)
    font(c, 40, 45, f'PRIVATE  |  Source: USDA FSA registered field maps  |  Basemap: {source_label}', 9, GRAY)
    font(c, 40, 28, 'Boundary illustrations are not legal surveys. Only georeferenced, matched FSA fields are depicted.', 9, GRAY)
    c.setFont('Helvetica', 9)
    c.setFillColor(GRAY)
    c.drawRightString(1185, 45, f'{base.upper()}  |  {page_num}')


def coord_box(bounds, frame):
    minx, miny, maxx, maxy = bounds
    x0, y0, width, height = frame
    def project(lon,lat):
        xx,yy=TO_MERC.transform(lon,lat)
        return (x0 + (xx-minx)/(maxx-minx)*width,
                y0 + (yy-miny)/(maxy-miny)*height)
    return project


def rings(geometry):
    if geometry.geom_type == 'Polygon':
        polygons = [geometry]
    else:
        polygons = list(geometry.geoms)
    for geom in polygons:
        yield list(geom.exterior.coords)
        for hole in geom.interiors:
            yield list(hole.coords)


def draw_shape(c, geometry, cvt, outline, width=2, fillalpha=0, fillcolor=None):
    p = c.beginPath()
    for ring in rings(geometry):
        for i, (lon, lat) in enumerate(ring):
            x, y = cvt(lon, lat)
            if i == 0:
                p.moveTo(x, y)
            else:
                p.lineTo(x, y)
        p.close()
    c.saveState()
    c.setStrokeColor(outline)
    c.setLineWidth(width)
    if fillalpha:
        c.setFillColor(fillcolor or outline)
        c.setFillAlpha(fillalpha)
    c.drawPath(p, stroke=1, fill=int(bool(fillalpha)), fillMode=0)
    c.restoreState()


def fixed_bbox(points, ratio, pad_fraction=.08, min_m=0):
    # A Web Mercator extent of the same exact aspect ratio as the raster and
    # PDF map frame; source geometry remains geographic WGS84 in GeoJSON.
    projected=[TO_MERC.transform(lon,lat) for lon,lat in points]
    minx=min(x for x,_ in projected);maxx=max(x for x,_ in projected)
    miny=min(y for _,y in projected);maxy=max(y for _,y in projected)
    midx=(minx+maxx)/2;midy=(miny+maxy)/2
    midlat=FROM_MERC.transform(midx,midy)[1]
    merc_min_m=min_m/math.cos(math.radians(midlat))
    east_span = max((maxx-minx)*(1+2*pad_fraction), merc_min_m)
    north_span = max((maxy-miny)*(1+2*pad_fraction), merc_min_m)
    east_span = max(east_span, north_span*ratio)
    north_span = east_span/ratio
    return (midx-east_span/2,midy-north_span/2,midx+east_span/2,midy+north_span/2)


def frame_img(c, image, box):
    x, y, w, h = box
    c.drawImage(ImageReader(image), x, y, width=w, height=h, mask='auto')
    c.setStrokeColor(colors.HexColor('#CAD5DB'))
    c.rect(x, y, w, h, stroke=1, fill=0)


def bar_and_north(c, bounds, frame):
    # Horizontal distance at map mid-latitude, approximate map scale for overview.
    minx, miny, maxx, maxy = bounds
    x, y, w, h = frame
    midlat=FROM_MERC.transform((minx+maxx)/2,(miny+maxy)/2)[1]
    km_per_px=(maxx-minx)*math.cos(math.radians(midlat))/(1000*w)
    target_px = 125
    target_km = target_px*km_per_px
    decade = 10**math.floor(math.log10(target_km))
    distance = min((1, 2, 5, 10), key=lambda v: abs(v*decade-target_km))*decade
    actual_px = distance/km_per_px
    barx, bary = x+20, y+22
    c.setFillColor(colors.white)
    c.roundRect(barx-9, bary-12, actual_px+60, 45, 4, fill=1, stroke=0)
    c.setStrokeColor(NAVY);c.setLineWidth(3)
    c.line(barx, bary, barx+actual_px, bary)
    for x1 in [barx,barx+actual_px]: c.line(x1,bary-5,x1,bary+5)
    units = f'{distance:g} km' if distance>=.5 else f'{distance*1000:g} m'
    font(c,barx,bary+12,units,9,NAVY,True)
    c.setFillColor(colors.white)
    c.circle(x+w-32, y+h-32, 19, fill=1, stroke=0)
    font(c,x+w-36,y+h-27,'N',12,NAVY,True)
    p=c.beginPath();p.moveTo(x+w-32,y+h-17);p.lineTo(x+w-39,y+h-29);p.lineTo(x+w-25,y+h-29);p.close()
    c.setFillColor(NAVY);c.drawPath(p,fill=1,stroke=0)


def get_roster():
    result = defaultdict(dict)
    for county in COUNTIES:
        path=SOURCE/'Producers by County'/f'{county} County_Producers.xlsx'
        if not path.exists():
            matches=list((SOURCE/'Producers by County').glob(f'{county} County_Producers*'))
            path=next(p for p in matches if p.suffix=='.xlsx')
        from openpyxl import load_workbook
        ws=load_workbook(path,read_only=True,data_only=True).active
        for row in ws.iter_rows(max_col=6,values_only=True,min_row=2):
            fid=row[2]
            if fid is None: continue
            fid=str(int(fid)) if isinstance(fid,(int,float)) else str(fid).strip()
            first=str(row[0] or '').strip();last=str(row[1] or '').strip()
            record=result[county].setdefault(fid,{'name':(first+' '+last).strip(),'tracts':set(),'fields':set()})
            if row[3] is not None: record['tracts'].add(str(row[3]))
            if row[4] is not None: record['fields'].add(str(row[4]))
    # The Florence AMP workbook identifies Anthony Jackson's Farm 8185,
    # Tract 2352, Field 2. Anthony's scanned FSA source map identifies the
    # physical county as Darlington and its four field acreages exactly match
    # the separately supplied registered Dread Marley GeoPDF. Place the
    # georeferenced fields in *their physical county*, retaining the original
    # workbook county and source provenance instead of changing enrollment.
    amp = result['Florence'].get('8185')
    if not amp or amp['tracts'] != {'2352'} or '2' not in amp['fields']:
        raise ValueError('Anthony Jackson workbook cross-reference changed')
    if '8185' in result['Darlington']:
        raise ValueError('Farm 8185 conflicts with Darlington roster')
    result['Darlington']['8185'] = dict(amp, amp_roster_county='Florence',
        source_registration_note='Darlington source FSA map and Florence AMP roster show Farm 8185 / Tract 2352 / Field 2; four source field acreages match.')
    return result


def field_features():
    old=json.loads((ROOT/'geojson/master_fsa_fields_geopdf_verified.geojson').read_text())['features']
    roster=get_roster();eligible=[];qa=[]
    for f in old:
        p=f['properties'];county=p['county'];fid=str(p['farm_id'])
        if county not in roster or fid not in roster[county]:
            continue
        source=SOURCE/p['source_pdf']
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=p['source_sha256']:
            raise ValueError('Source SHA changed: '+str(source))
        d=fitz.open(source);page=d[p['page_number']-1]
        geom=registered_vector(d,page,p['source_draw_index'])
        acres=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
        error=100*(acres/float(p['fsa_reported_acres'])-1)
        if abs(error)>2:
            raise ValueError(f'FSA printed area mismatch for {fid} field {p["field_id"]}: {error:.1f}%')
        selected = str(p['field_id']) in roster[county][fid]['fields']
        out={'type':'Feature','properties':dict(p,producer=roster[county][fid]['name'],
            amp_roster_county=roster[county][fid].get('amp_roster_county', county),
            source_registration_note=roster[county][fid].get('source_registration_note', ''),
            calculated_acres=round(acres,3),area_error_percent=round(error,2),
            county_workbook_selected=selected,
            status='NATIVE_GEOPDF_REFERENCED_FIELD__NOT_SURVEY'), 'geometry':mapping(geom)}
        eligible.append(out)
        qa.append({'county':county,'farm_id':fid,'field_id':p['field_id'],'source_pdf':p['source_pdf'],
                   'fsa_acres':p['fsa_reported_acres'],'geo_acres':round(acres,3),'area_error_pct':round(error,2),
                   'recorded_in_county_sheet':True,
                   'field_listed_in_county_sheet':selected,
                   'amp_roster_county':roster[county][fid].get('amp_roster_county', county),
                   'boundary_method':'native_geopdf_vector'})
        print('REGISTERED',county,fid,p['field_id'],round(acres,2),flush=True)
    registered=ROOT/'geojson/registered_scanned_fields.geojson'
    if registered.exists():
        for f in json.loads(registered.read_text())['features']:
            p=f['properties'];county=p['county'];fid=str(p['farm_id'])
            if fid not in roster[county] or p['tract_id'] not in roster[county][fid]['tracts']:
                raise ValueError('Scanned field does not match producer workbook farm/tract: '+fid)
            if p['county_workbook_selected'] != (str(p['field_id']) in roster[county][fid]['fields']):
                raise ValueError('Scanned source field selection does not match producer workbook')
            if hashlib.sha256((SOURCE/p['source_pdf']).read_bytes()).hexdigest()!=p['source_sha256']:
                raise ValueError('Scanned PDF source SHA mismatch: '+fid)
            geom=shape(f['geometry'])
            if not geom.is_valid or geom.area<=0:
                raise ValueError('Scanned FSA geometry is not valid')
            acres=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
            error=100*(acres/float(p['fsa_reported_acres'])-1)
            # Small source-map crops can have fewer than 100 features even when
            # six independently fetched NAIP extents agree at sub-meter scale.
            # Admit 60+ inliers only if sub-half-pixel source-image residuals
            # also support the cross-tile and FSA printed-acreage checks.
            inliers=p['image_registration_inliers']
            high_precision_small_map=(inliers>=60 and p['image_registration_rmse_px']<=0.5)
            if p.get('registration_crosscheck_method'):
                # Old FSA scans can only be registered against historical
                # imagery. Do not label repeat-split model stability as an
                # independent satellite-tile or field-survey accuracy result.
                if not (inliers>=200 and
                        p.get('resampled_vertex_p95_m', 999)>0 and
                        p['resampled_vertex_p95_m']<=1 and
                        p['image_registration_rmse_px']<=2 and
                        abs(error)<=2):
                    raise ValueError('Archived FSA source / Wayback repeated-fit QA fails: '+fid)
            elif abs(error)>2 or (inliers<100 and not high_precision_small_map) or p['independent_tile_rmse_m']>1:
                raise ValueError('Scanned FSA registration fails acreage/independent tile QA: '+fid)
            p['calculated_acres']=round(acres,3);p['area_error_percent']=round(error,2)
            eligible.append(f)
            qa.append({'county':county,'farm_id':fid,'field_id':p['field_id'],'source_pdf':p['source_pdf'],
                       'fsa_acres':p['fsa_reported_acres'],'geo_acres':round(acres,3),
                       'area_error_pct':round(error,2),'recorded_in_county_sheet':True,
                       'field_listed_in_county_sheet':p['county_workbook_selected'],
                       'amp_roster_county':county,'boundary_method':'raster_georeg_manually_traced'})
            print('RASTER_REGISTERED',county,fid,p['field_id'],round(acres,2),flush=True)
    return eligible,qa,roster


def county_geom():
    # Pin the exact Census-derived six county boundaries in the private repo.
    # A transient raw.githubusercontent.com timeout must never prevent producing
    # a county atlas, or silently substitute a guessed boundary.
    all_counties=json.loads((ROOT/'geojson/sc_counties_for_verified_atlases.geojson').read_text())['features']
    return {county:shape(next(f['geometry'] for f in all_counties if str(f['id']).zfill(5)==fips))
            for county,fips in COUNTIES.items()}


def draw_county(c,county,farms,boundary,basetype,source_tracker):
    frame=(39,117,853,532)
    pts=[]
    for r in rings(boundary):pts.extend(r)
    bounds=fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.1)
    im,attribution=fetch_image(bounds,1706,1064,basetype)
    source_tracker.add(attribution)
    common(c,county,basetype,'01  /  County overview  /  Actual FSA-derived field locations',1,attribution)
    frame_img(c,im,frame)
    cvt=coord_box(bounds,frame)
    draw_shape(c,boundary,cvt,colors.white,width=3.7)
    draw_shape(c,boundary,cvt,NAVY,width=1.5)
    placed=[]
    for ix,(fid,fields) in enumerate(sorted(farms.items())):
        color=colors.HexColor(PALETTE[ix])
        chosen=[f for f in fields if f['properties']['county_workbook_selected']]
        points=[shape(f['geometry']).representative_point() for f in (chosen or fields)]
        lon=sum(p.x for p in points)/len(points);lat=sum(p.y for p in points)/len(points)
        anchor_x,anchor_y=cvt(lon,lat)
        x,y=anchor_x,anchor_y
        # Farm IDs that overlap at county scale need distinct index bubbles.
        offsets=[(0,0),(28,25),(-28,25),(28,-25),(-28,-25),
                 (45,0),(-45,0),(0,45),(0,-45)]
        for off_x,off_y in offsets:
            test_x,test_y=anchor_x+off_x,anchor_y+off_y
            if not (frame[0]+14<test_x<frame[0]+frame[2]-14 and
                    frame[1]+14<test_y<frame[1]+frame[3]-14):
                continue
            if all(math.hypot(test_x-px,test_y-py)>=27 for px,py in placed):
                x,y=test_x,test_y
                break
        if math.hypot(x-anchor_x,y-anchor_y)>2:
            c.setStrokeColor(colors.white);c.setLineWidth(3.2)
            c.line(anchor_x,anchor_y,x,y)
            c.setStrokeColor(color);c.setLineWidth(1.7)
            c.line(anchor_x,anchor_y,x,y)
        c.setFillColor(colors.white);c.circle(x,y,13,stroke=0,fill=1)
        c.setFillColor(color);c.circle(x,y,10.5,stroke=0,fill=1)
        c.setFillColor(colors.white);c.setFont('Helvetica-Bold',10)
        c.drawCentredString(x,y-3.5,str(ix+1))
        placed.append((x,y))
    bar_and_north(c,bounds,frame)
    font(c,919,621,'FARM INDEX',12,NAVY,True)
    yy=588
    for ix,(fid,fields) in enumerate(sorted(farms.items())):
        color=colors.HexColor(PALETTE[ix]);p=fields[0]['properties']
        c.setFillColor(color);c.roundRect(923,yy-8,17,17,3,fill=1,stroke=0)
        font(c,950,yy-3,f'{ix+1:02d}  FARM {fid}',12,NAVY,True)
        yy=wrap(c,p['producer'],923,yy-30,260,11,14)
        if p['amp_roster_county'] != county:
            yy=wrap(c,f'AMP roster: {p["amp_roster_county"]}; FSA physical map: {county}',923,yy-3,260,9,13,GRAY)
        selected=sum(bool(f['properties']['county_workbook_selected']) for f in fields)
        yy=wrap(c,f'{selected} county-sheet field(s); {len(fields)-selected} additional FSA context fields',923,yy-4,260,10,14,GRAY)-(0 if len(farms)>=7 else 12 if len(farms)>=5 else 28)
    yy=wrap(c,'Markers represent locations computed from georeferenced FSA field polygons, not reported residential addresses.',923,yy-5,260,10,14,GRAY)
    font(c,922,137,'County boundary: U.S. Census cartographic GeoJSON',8,GRAY)
    c.showPage()


def draw_detail(c,county,farms,fid,fields,basetype,number,source_tracker):
    idx=list(sorted(farms)).index(fid)
    color=colors.HexColor(PALETTE[idx]);p=fields[0]['properties']
    frame=(39,119,853,532)
    points=[]
    for f in fields:
        for ring in rings(shape(f['geometry'])):points.extend(ring)
    bounds=fixed_bbox(points,frame[2]/frame[3],pad_fraction=.19,min_m=420)
    im,attribution=fetch_image(bounds,1706,1064,basetype)
    source_tracker.add(attribution)
    common(c,county,basetype,f'{number:02d}  /  Farm {fid}  /  Source field boundaries over {basetype.lower()} imagery',number,attribution)
    frame_img(c,im,frame)
    cvt=coord_box(bounds,frame)
    for f in fields:
        geom=shape(f['geometry'])
        selected=f['properties']['county_workbook_selected']
        draw_shape(c,geom,cvt,color if selected else colors.HexColor('#D9E2E7'),
                   width=3.2 if selected else 1.5,fillalpha=.26 if selected else 0)
        point=geom.representative_point();x,y=cvt(point.x,point.y)
        text=f"{f['properties']['field_id']}"
        c.setFillColor(colors.white);c.roundRect(x-11,y-8,22,16,4,stroke=0,fill=1)
        c.setFillColor(NAVY if selected else GRAY);c.setFont('Helvetica-Bold',9)
        c.drawCentredString(x,y-3,text)
    bar_and_north(c,bounds,frame)
    font(c,923,623,f'FARM {fid}',17,NAVY,True)
    wrap(c,p['producer'],923,600,250,12,17)
    origin=p['amp_roster_county']
    font(c,923,562,'AMP REGISTERED FIELD' if origin==county else f'AMP SELECTED FIELD ({origin.upper()} ROSTER)',10,GRAY,True)
    c.setFillColor(color);c.roundRect(923,536,18,18,3,stroke=0,fill=1)
    font(c,951,540,'Farm ID color',10,NAVY)
    yy=512
    chosen=[f for f in fields if f['properties']['county_workbook_selected']]
    for f in sorted(chosen,key=lambda f:str(f['properties']['field_id'])):
        prop=f['properties']
        font(c,923,yy,f"Field {prop['field_id']}",11,NAVY,True)
        font(c,1028,yy,f"{float(prop['fsa_reported_acres']):g} ac",10,GRAY)
        yy-=21
    yy-=16
    total=sum(float(f['properties']['fsa_reported_acres']) for f in chosen)
    font(c,923,yy,f'Selected source area: {total:.2f} ac',11,NAVY,True)
    yy-=30
    context=[f for f in fields if not f['properties']['county_workbook_selected']]
    if context:
        yy=wrap(c,f'{len(context)} other FSA fields are outlined in white/gray for context only; they are not identified as AMP-selected in this county workbook.',923,yy,250,10,15,GRAY)-15
    if origin != county:
        yy=wrap(c,f'Important: the AMP spreadsheet lists {origin} County, but both source FSA maps identify Darlington County and exactly match Farm 8185, Tract 2352, field acreages.',923,yy,250,9,13,GRAY)-12
    method=p.get('method','')
    if 'raster' in method.lower():
        if 'Wayback' in method:
            explain=f"2016 FSA aerial image matched to historical 2015 Esri Wayback using {p['image_registration_inliers']} image features. Field outlines traced from source boundaries and checked against printed acres. Approximate, not surveyed."
        else:
            explain=f"FSA aerial image matched to USGS NAIP using {p['image_registration_inliers']} image features. Field outlines traced from source boundaries and checked against printed acres. Approximate, not surveyed."
        yy=wrap(c,explain,923,yy,250,9,13,GRAY)-12
    else:
        yy=wrap(c,'Boundaries were reproduced from native FSA GeoPDF vector paths and mapped using the PDF geographic reference.',923,yy,250,10,15,GRAY)-18
    yy=wrap(c,'Source-image date and current land cover can differ from the displayed basemap date.',923,yy,250,10,15,GRAY)
    font(c,923,137,'GeoJSON WGS84  |  Map EPSG:3857  |  Area checked to FSA label',8,GRAY)
    c.showPage()


def example_qgis_polygon():
    """A distinct user QGIS example site, never label it a verified FSA farm."""
    source=SOURCE/'Producers by County/Satelite Maps/Allendale County.pdf'
    d=fitz.open(source);p=d[0]
    vp_refs=d.xref_get_key(p.xref,'VP')[1]
    vp=d.xref_object(int(nums(vp_refs)[0]))
    bbox=nums(re.search(r'/BBox\s*\[([^]]+)\]',vp).group(1))
    m=int(re.search(r'/Measure\s+(\d+)\s+0\s+R',vp).group(1))
    ref=nums(d.xref_get_key(m,'GPTS')[1])
    north,west,south,_,__,east,___,____=ref
    assert 32.9<south<north<33.1 and -81.5<west<east<-81.2
    drawing=next(a for a in p.get_drawings() if a['fill'] is not None and
                 .60<a['fill'][0]<.70 and .40<a['fill'][1]<.50)
    vertices=[(segment[1].x,segment[1].y) for segment in drawing['items'] if segment[0]=='l']
    coords=[]
    for x,y in vertices:
        lon=west+(x-bbox[0])/(bbox[2]-bbox[0])*(east-west)
        lat=north-y/p.rect.height*(north-south)
        coords.append((lon,lat))
    geom=Polygon(coords)
    if not geom.is_valid or geom.area<=0:raise ValueError('Allendale example polygon is invalid')
    acres=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
    return geom,acres


def make_allendale_reference(outlines):
    """Produce real background atlas for supplied SINGLE combined QGIS site only."""
    geom,acres=example_qgis_polygon()
    place=OUTPUT/'Allendale_QGIS_Example_Only'
    place.mkdir(exist_ok=True)
    feature={'type':'Feature','geometry':mapping(geom),'properties':{
        'county':'Allendale', 'producer_names':'Tiffany Loadholt and Samuel Lance Jr.',
        'polygon_source':'Supplied QGIS Allendale County.pdf, native georeferenced vector path',
        'estimated_digital_area_acres':round(acres,2),
        'status':'EXAMPLE_COMBINED_AREA__NOT_SPLIT_BY_FARM__NOT_FSA_FIELD_VERIFIED'}}
    (place/'Allendale_QGIS_Example_Combined_Site.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[feature]},indent=2))
    results=[]
    boundary=outlines['Allendale']
    for basetype in ('Satellite','Topography'):
        name=f'Allendale_QGIS_Example_{basetype}.pdf'
        pdf=place/name
        c=canvas.Canvas(str(pdf),pagesize=(W,H),pageCompression=1)
        c.setTitle(f'Allendale example combined site, {basetype}; farm-level registration unresolved')
        sources=set()
        frame=(39,118,853,531)
        pts=[v for ring in rings(boundary) for v in ring]
        bounds=fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.09)
        im,provider=fetch_image(bounds,1706,1064,basetype);sources.add(provider)
        common(c,'Allendale',basetype,'01 / County overview / User-supplied QGIS example site only',1,provider)
        frame_img(c,im,frame);cvt=coord_box(bounds,frame)
        draw_shape(c,boundary,cvt,colors.white,width=3.5)
        draw_shape(c,boundary,cvt,NAVY,width=1.4)
        pt=geom.representative_point();x,y=cvt(pt.x,pt.y)
        c.setFillColor(colors.white);c.circle(x,y,12,fill=1,stroke=0)
        c.setFillColor(colors.HexColor(PALETTE[0]));c.circle(x,y,9,fill=1,stroke=0)
        bar_and_north(c,bounds,frame)
        font(c,920,620,'COMBINED EXAMPLE AREA',12,NAVY,True)
        y=wrap(c,'Tiffany Loadholt and Samuel Lance Jr.',920,586,260,11,16)-24
        y=wrap(c,f'One combined {acres:.1f}-acre polygon extracted from the user-provided geospatial QGIS PDF.',920,y,260,10,16)-25
        wrap(c,'Important: this is NOT two independently verified Farm ID boundaries. The two photographed FSA maps cannot be placed independently using the supplied coordinates.',920,y,260,10,16,GRAY)
        c.showPage()
        pts=list(geom.exterior.coords)
        bounds=fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.38,min_m=500)
        im,provider=fetch_image(bounds,1706,1064,basetype);sources.add(provider)
        common(c,'Allendale',basetype,'02 / Zoom / Combined QGIS example polygon over new geographic basemap',2,provider)
        frame_img(c,im,frame);cvt=coord_box(bounds,frame)
        color=colors.HexColor(PALETTE[0]);draw_shape(c,geom,cvt,color,width=3.3,fillalpha=.25)
        bar_and_north(c,bounds,frame)
        font(c,920,618,'USER EXAMPLE FOOTPRINT',12,NAVY,True)
        y=wrap(c,f'{acres:.1f} acres, calculated from the QGIS example PDF polygon.',920,585,255,11,16)-23
        y=wrap(c,'Map overlay is georeferenced. The source outlines for Tiffany Farm 3779 and Samuel Farm 3740 still require separate field-site registration.',920,y,255,10,16,GRAY)-25
        wrap(c,'This page is an illustration of the requested style, not a substitute for independently verified FSA farm polygons.',920,y,255,10,16,GRAY)
        c.showPage();c.save()
        results.append({'file':str(pdf.relative_to(OUTPUT)),'pages':2,'status':'QGIS_EXAMPLE_NOT_FARM_REGISTERED','providers':sorted(sources)})
        print('BUILT EXAMPLE',pdf,flush=True)
    return results


def main():
    OUTPUT.mkdir(exist_ok=True,parents=True)
    features,qa,roster=field_features()
    outlines=county_geom()
    grouped=defaultdict(lambda:defaultdict(list))
    for f in features:
        p=f['properties'];county=p['county'];fid=str(p['farm_id'])
        if not outlines[county].covers(shape(f['geometry']).representative_point()):
            raise ValueError(f'Farm {fid} verified polygon outside workbook county {county}')
        grouped[county][fid].append(f)
    with (OUTPUT/'source_area_validation.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(qa[0]));writer.writeheader();writer.writerows(qa)
    (OUTPUT/'verified_fsa_fields.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2))
    manifest=[]
    for county,farms in sorted(grouped.items()):
        county_dir=OUTPUT/county;county_dir.mkdir(exist_ok=True)
        county_features=[f for fs in farms.values() for f in fs]
        (county_dir/f'{county}_Registered_Fields.geojson').write_text(json.dumps({'type':'FeatureCollection','features':county_features},indent=2))
        for basetype in ('Satellite','Topography'):
            filename=f'{county}_County_{basetype}.pdf'
            pdf=county_dir/filename
            c=canvas.Canvas(str(pdf),pagesize=(W,H),pageCompression=1)
            c.setTitle(f'{county} County AMP / FSA Registered Field Atlas - {basetype}')
            c.setAuthor('SCSU AMP / FSA geospatial boundary reconstruction')
            sources=set()
            draw_county(c,county,farms,outlines[county],basetype,sources)
            for n,(fid,fields) in enumerate(sorted(farms.items()),2):
                draw_detail(c,county,farms,fid,fields,basetype,n,sources)
            c.save()
            d=fitz.open(pdf)
            if len(d)!=1+len(farms):raise ValueError('Missing detail atlas pages')
            if pdf.stat().st_size<55000:raise ValueError('Atlas suspiciously empty')
            manifest.append({'county':county,'basemap':basetype,'file':str(pdf.relative_to(OUTPUT)),
                             'farms':len(farms),'fields':len(county_features),'pages':len(d),
                             'size_bytes':pdf.stat().st_size,'providers':sorted(sources)})
            print('BUILT',pdf,'pages',len(d),'KB',round(pdf.stat().st_size/1024),flush=True)
    example_files=make_allendale_reference(outlines)
    (OUTPUT/'manifest.json').write_text(json.dumps({'status':'VERIFIED_SUBSET_ONLY__NOT_ALL_AMP_FARMS',
      'warning':'Most supplied photographed FSA maps lack native spatial references; unregistered shapes excluded.',
      'atlas_files':manifest,'verified_farm_count':sum(len(x) for x in grouped.values()),
      'verified_field_count':len(features),'separate_allendale_qgis_examples':example_files},indent=2))
    with zipfile.ZipFile(OUTPUT/'SCSU_AMP_Verified_Registered_Atlases.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in OUTPUT.rglob('*'):
            if path.is_file() and path.suffix.lower() in ('.pdf','.geojson','.csv','.json'):
                z.write(path,path.relative_to(OUTPUT))
    print('COMPLETE',len(manifest),'PDFs',len(features),'registered fields',flush=True)


if __name__=='__main__':main()
