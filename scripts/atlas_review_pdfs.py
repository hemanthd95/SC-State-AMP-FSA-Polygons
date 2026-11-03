"""Produce private source-review atlases. These are not final basemap atlases."""
import colorsys
import csv
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

import pymupdf
from PIL import Image
from pyproj import Transformer
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from shapely.geometry import Point, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
WORK = Path('/workspace/amp-atlas-work')
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
WIDTH, HEIGHT = 1224, 792
NAVY = colors.HexColor('#152E40')
GRAY = colors.HexColor('#52616B')
GOLD = colors.HexColor('#A65E16')
RED = colors.HexColor('#A43131')
project = Transformer.from_crs(4326, 32617, always_xy=True)


def text(c, x, y, value, size=10, color=NAVY, bold=False):
    c.setFillColor(color)
    c.setFont('Helvetica-Bold' if bold else 'Helvetica', size)
    c.drawString(x, y, str(value))


def paragraph(c, value, x, y, width, size=11, color=NAVY, leading=None):
    leading = leading or size * 1.45
    for line in simpleSplit(str(value), 'Helvetica', size, width):
        text(c, x, y, line, size, color)
        y -= leading
    return y


def header(c, county, subtitle, page):
    c.setFillColor(NAVY); c.rect(0, HEIGHT-12, WIDTH, 12, fill=1, stroke=0)
    text(c, 36, 752, 'SOUTH CAROLINA AMP / FSA', 11, bold=True)
    text(c, 36, 716, f'{county} County' if county != 'Unassigned' else 'County assignment pending', 27, bold=True)
    text(c, 36, 691, subtitle, 12, GRAY)
    c.setStrokeColor(colors.HexColor('#CFD8DE')); c.line(36, 679, 1188, 679)
    text(c, 36, 50, 'PRIVATE  |  SCSU 1890 Public Service and Agriculture  |  Source review, 2026-11-03', 9, GRAY)
    text(c, 36, 32, 'Registration, source identity and enrollment scope exceptions remain. Not a final satellite or topographic atlas.', 9, RED)
    c.setFont('Helvetica', 9); c.setFillColor(GRAY); c.drawRightString(1188, 50, f'Page {page}')


def path_polygon(c, geometry, convert, fill, stroke, line_width=1):
    polys = [geometry] if geometry.geom_type == 'Polygon' else list(geometry.geoms)
    for polygon in polys:
        p = c.beginPath()
        for ring in [polygon.exterior, *polygon.interiors]:
            coords = list(ring.coords)
            p.moveTo(*convert(*coords[0]))
            for xy in coords[1:]: p.lineTo(*convert(*xy))
            p.close()
        c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(line_width)
        c.drawPath(p, fill=1, stroke=1, fillMode=0)


def county_map(c, county, farms, boundaries, points, frame):
    x, y, w, h = frame
    c.setFillColor(colors.HexColor('#F4F7F7')); c.setStrokeColor(colors.HexColor('#CED7DC'))
    c.rect(x, y, w, h, fill=1, stroke=1)
    if county not in boundaries:
        paragraph(c, 'No county boundary can be assigned until the county is reconciled.', x+30, y+h-50, w-60, 14)
        return
    geom = transform(project.transform, boundaries[county])
    minx, miny, maxx, maxy = geom.bounds
    scale = min((w-80)/(maxx-minx), (h-80)/(maxy-miny))
    ox = x + (w-(maxx-minx)*scale)/2
    oy = y + (h-(maxy-miny)*scale)/2
    conv = lambda e, n: (ox+(e-minx)*scale, oy+(n-miny)*scale)
    c.saveState()
    clip = c.beginPath(); clip.rect(x+1,y+1,w-2,h-2); c.clipPath(clip,stroke=0,fill=0)
    path_polygon(c, geom, conv, colors.HexColor('#E6EEE5'), NAVY, 1.2)
    # Locations remain fixed. Leader labels move to avoid concealing co-located markers.
    used = []
    for farm in farms:
        point = points.get((county, farm['farm_id']))
        if not point or point['geometry'] is None:
            continue
        lon, lat = point['geometry']['coordinates']
        e, n = project.transform(lon, lat); px, py = conv(e,n)
        if not (x+5 < px < x+w-5 and y+5 < py < y+h-5):
            continue
        verified = point['properties']['location_status'].startswith('REGISTERED')
        color = colors.Color(*farm['color'])
        c.setStrokeColor(color); c.setFillColor(color if verified else colors.white); c.setLineWidth(1.4)
        c.circle(px,py,4,stroke=1,fill=1)
        lx,ly=px+12,py+12
        for attempt in range(100):
            radius=15+8*(attempt//8); angle=attempt*math.pi/4
            lx=max(x+12,min(x+w-12,px+radius*math.cos(angle)))
            ly=max(y+12,min(y+h-12,py+radius*math.sin(angle)))
            if all(math.hypot(lx-a,ly-b)>20 for a,b in used): break
        used.append((lx,ly))
        c.setStrokeColor(color); c.setLineWidth(.6); c.line(px,py,lx,ly)
        c.setFillColor(colors.white); c.circle(lx,ly,8,stroke=1,fill=1)
        c.setFillColor(NAVY); c.setFont('Helvetica-Bold',8); c.drawCentredString(lx,ly-3,str(farm['number']))
    c.restoreState()
    # True north direction computed in projected coordinates at county center.
    center = boundaries[county].representative_point()
    a = project.transform(center.x,center.y); b=project.transform(center.x,center.y+.001)
    angle=math.atan2(b[1]-a[1],b[0]-a[0])
    nx,ny=x+w-35,y+h-62
    dx,dy=26*math.cos(angle),26*math.sin(angle)
    c.setStrokeColor(NAVY); c.setLineWidth(1.8); c.line(nx,ny,nx+dx,ny+dy)
    text(c,nx-4,ny+dy+10,'N',11,bold=True)
    # UTM meter scale; choose a round kilometer length.
    target=120/scale/1000
    units=max(v for v in [.1,.2,.5,1,2,5,10,20,50,100] if v<=target)
    length=units*1000*scale; sx=x+24; sy=y+23
    c.setFillColor(NAVY);c.rect(sx,sy,length/2,5,fill=1,stroke=0)
    c.setFillColor(colors.white);c.setStrokeColor(NAVY);c.rect(sx+length/2,sy,length/2,5,fill=1,stroke=1)
    text(c,sx,sy+10,f'0                         {units:g} km',8)
    text(c,x+20,y+h-21,'Census county boundary / location audit',9,GRAY)


def scope_label(farm):
    labels={'county_workbook':'county workbook','enrollment_year_2':'Year 2 enrollment','enrollment_year_1':'Year 1 enrollment'}
    return ', '.join(labels.get(s,s) for s in farm['scopes']) or 'Enrollment record; Farm ID pending'


def overview(c,county,farms,boundaries,points,page):
    count=sum(not f.get('missing_id') for f in farms)
    header(c,county,f'SOURCE REVIEW  |  {count} listed county/Farm-ID combinations; current and historical scope distinguished',page)
    county_map(c,county,farms,boundaries,points,(36,112,752,548))
    text(c,812,642,'FARM INDEX',13,bold=True)
    text(c,812,622,'C: county workbook   Y2: enrollment Year 2   Y1: Year 1',9,GRAY)
    yy=600
    for f in farms:
        point=points.get((county,f['farm_id']))
        usable=bool(point and point['geometry'])
        c.setFillColor(colors.Color(*f['color']) if usable else colors.white)
        c.setStrokeColor(colors.Color(*f['color']) if usable else RED)
        c.circle(821,yy+3,5,stroke=1,fill=1)
        codes='/'.join({'county_workbook':'C','enrollment_year_2':'Y2','enrollment_year_1':'Y1'}.get(s,s) for s in f['scopes'])
        label=(f"{f['number']:02d}  Farm {f['farm_id']}  [{codes}]" if not f.get('missing_id') else f"{f['number']:02d}  Farm ID pending / {f['producer_ref']}")
        text(c,835,yy,label,9,NAVY if usable else RED)
        yy-=13
    text(c,812,max(yy-14,96),'Unfilled index symbols: location withheld or unresolved.',8,RED)
    paragraph(c,'Filled map dots: representative points of registered source polygons. Hollow dots: approximate reported coordinates. Outside-county or missing coordinates are listed in the index without invented map locations.',36,94,1140,8,GRAY,10)
    c.showPage()


def registered_image(farm,fields):
    members=[f for f in fields if f['properties']['county']==farm['county'] and str(f['properties']['farm_id'])==farm['farm_id']]
    if not members:return None
    source=members[0]['properties']['source_pdf']
    target=WORK/'registered_insets'/f"{farm['county']}_{farm['farm_id']}.jpg";target.parent.mkdir(exist_ok=True)
    if target.exists():
        return {'source':source,'page':members[0]['properties']['page_number'],'image_file':str(target),
                'match_method':'SOURCE_VECTOR_AND_GDAL_REFERENCE_CHECKED','registered':True}
    path=SOURCE/source;doc=pymupdf.open(path);page=doc[members[0]['properties']['page_number']-1]
    vp=doc.xref_get_key(page.xref,'VP')[1]
    values=list(map(float,re.search(r'/BBox\s*\[([^]]+)\]',vp).group(1).split()))
    clip=pymupdf.Rect(min(values[0],values[2]),page.rect.height-max(values[1],values[3]),max(values[0],values[2]),page.rect.height-min(values[1],values[3]))
    drawings=page.get_drawings()
    for member in members:
        draw=drawings[member['properties']['source_draw_index']]
        vertices=[item[1] for item in draw['items'] if item[0]=='l']
        if vertices:
            page.draw_polyline(vertices,color=tuple(farm['color']),fill=tuple(farm['color']),fill_opacity=.10,width=1.2,closePath=True,overlay=True)
    page.get_pixmap(dpi=180,clip=clip,alpha=False).save(target,jpg_quality=92)
    return {'source':source,'page':members[0]['properties']['page_number'],'image_file':str(target),
            'match_method':'SOURCE_VECTOR_AND_GDAL_REFERENCE_CHECKED','registered':True}


def draw_inset(c,match,frame):
    x,y,w,h=frame
    c.setFillColor(colors.HexColor('#F4F6F7'));c.setStrokeColor(colors.HexColor('#CCD6DD'));c.rect(x,y,w,h,stroke=1,fill=1)
    cache=WORK/'review_insets';cache.mkdir(exist_ok=True)
    key=hashlib.sha256((match['image_file']+str(w)+str(h)+str(match.get('registered',False))).encode()).hexdigest()
    jpeg=cache/(key+'.jpg')
    if not jpeg.exists():
        im=Image.open(match['image_file']).convert('RGB')
        if not match.get('registered'):
            # Exclude source footer/contact annotations from the map-portion inset.
            bottom=.79 if match['source']=='Sonya_Ramsue_FSA_Map.pdf' else .84
            im=im.crop((0,int(im.height*.015),im.width,int(im.height*bottom)))
        # Retain print-size resolution and embed JPEG bytes directly (DCT).
        im.thumbnail((math.ceil(w*200/72),math.ceil(h*200/72)),Image.Resampling.LANCZOS)
        im.save(jpeg,format='JPEG',quality=90,optimize=True)
    im=Image.open(jpeg)
    factor=min((w-12)/im.width,(h-12)/im.height)
    iw,ih=im.width*factor,im.height*factor
    c.drawImage(str(jpeg),x+(w-iw)/2,y+(h-ih)/2,width=iw,height=ih)


def details(c,county,farm,fields,points,boundaries,start_page):
    matches=farm['source_matches']
    native=registered_image(farm,fields)
    if native:matches=[native]
    pages=[]
    chunks=[matches[i:i+2] for i in range(0,len(matches),2)] or [[]]
    for ci,chunk in enumerate(chunks):
        pageno=start_page+ci
        subtitle=(f"{farm['number']:02d} / Farm {farm['farm_id']}" if not farm.get('missing_id') else f"{farm['number']:02d} / Farm ID pending - {farm['producer_ref']}")
        header(c,county,subtitle+'  |  '+scope_label(farm),pageno)
        status=farm.get('extraction_status','FARM_ID_AND_LOCATION_UNRESOLVED')
        text(c,36,655,status.replace('_',' '),11,GOLD,bold=True)
        if not chunk:
            county_map(c,county,[farm],boundaries,points,(36,130,735,500))
            xx,yy=800,610
            yy=paragraph(c,'No confirmed FSA map is available for this inventory entry.',xx,yy,370,16,RED)
            if (county,farm['farm_id'])==('Orangeburg','11990'):
                yy=paragraph(c,'The named source PDF contains administrative farm records, not a field-boundary map. Contact and tax forms are excluded from this atlas.',xx,yy-18,370,11)
            yy=paragraph(c,'The county outline is a location audit only. No farm boundary has been fabricated.',xx,yy-22,370,12)
            yy=paragraph(c,'Reported coordinates are approximate. Outside-county and missing coordinates are withheld from the map.',xx,yy-22,370,11)
            paragraph(c,'Required: confirm the Farm ID, supply the corresponding field map, and establish a supported geographic reference.',xx,yy-22,370,11)
        elif len(chunk)==1:
            draw_inset(c,chunk[0],(36,120,735,510))
            match=chunk[0];xx,yy=800,610
            yy=paragraph(c,'Registered source-map inset' if match.get('registered') else 'Source-map inset; geographic registration pending',xx,yy,370,16,GOLD)
            yy=paragraph(c,match['source']+f" / page {match['page']}",xx,yy-18,370,11)
            yy=paragraph(c,match['match_method'].replace('_',' '),xx,yy-18,370,10,GRAY)
            if match.get('identity_warning'):
                yy=paragraph(c,match['identity_warning'],xx,yy-18,370,12,RED)
            yy=paragraph(c,'Tract IDs as supplied: '+', '.join(sorted({r['tract_id'] for r in farm['records'] if r['tract_id']})),xx,yy-18,370,11)
            yy=paragraph(c,'Field IDs as supplied: '+', '.join(sorted({r['field_id'] for r in farm['records'] if r['field_id']})),xx,yy-18,370,11)
            yy=paragraph(c,'Source-map fields may differ from program-enrolled fields. See the field reconciliation table.',xx,yy-18,370,11,GRAY)
            paragraph(c,'FSA map imagery and printed annotations are retained as source evidence. Image acquisition dates are not independently established. Source north arrows/scales apply only to their original insets.',xx,yy-18,370,10,GRAY)
        else:
            for i,match in enumerate(chunk):
                xx=36+i*588
                draw_inset(c,match,(xx,155,564,475))
                yy=paragraph(c,match['source']+f" / page {match['page']}",xx,139,564,9)
                text(c,xx,yy-2,'Source-map inset; geographic registration pending',10,GOLD,bold=True)
                paragraph(c,match['match_method'].replace('_',' '),xx,yy-18,564,8,GRAY)
        text(c,36,77,f"Inventory item {farm['number']:02d}  |  Source inset group {ci+1} of {len(chunks)}  |  No new basemap layer acquired",9,GRAY)
        c.showPage()
        pages.append(pageno)
    return pages


def main():
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    farms=json.loads((WORK/'farm_inventory_matched_private.json').read_text())
    missing=json.loads((WORK/'enrollment_records_missing_farm_id_private.json').read_text())
    fields=json.loads((OUT/'geojson/SC_AMP_FSA_All_Farm_Fields.geojson').read_text())['features']
    locations=json.loads((OUT/'geojson/SC_AMP_FSA_Farm_Locations.geojson').read_text())['features']
    points={(p['properties']['county'],str(p['properties']['farm_id'])):p for p in locations}
    counties=json.loads((OUT/'geojson/SC_County_Boundaries_Census_2022.geojson').read_text())['features']
    boundaries={f['properties']['NAME']:shape(f['geometry']) for f in counties}
    # Missing Farm IDs remain unresolved enrollment records, never invented IDs.
    for record in missing:
        farms.append({'county':record['county'] or 'Unassigned','farm_id':'ID_PENDING_'+record['amp_producer_id'],
                      'producer_ref':record['amp_producer_id'],'missing_id':True,
                      'scopes':[record['scope']],'records':[record],'source_matches':[],
                      'extraction_status':'FARM_ID_AND_SOURCE_ASSOCIATION_UNRESOLVED'})
    grouped=defaultdict(list)
    for farm in farms:grouped[farm['county']].append(farm)
    pdfdir=OUT/'source_review_pdfs';pdfdir.mkdir(exist_ok=True)
    page_log=[];county_log=[]
    # Orangeburg establishes the layout; the same renderer then handles all counties.
    order=sorted(grouped,key=lambda c:(c!='Orangeburg',c))
    for county in order:
        subset=sorted(grouped[county],key=lambda f:(f.get('missing_id',False),int(f['farm_id']) if f['farm_id'].isdigit() else 999999))
        for i,farm in enumerate(subset,1):
            farm['number']=i
            farm['color']=colorsys.hsv_to_rgb((i*.61803398875)%1,.72,.66)
        filename=pdfdir/f'{county}_County_Source_Review.pdf'
        c=canvas.Canvas(str(filename),pagesize=(WIDTH,HEIGHT),pageCompression=1)
        c.setTitle(f'{county} County AMP/FSA - Source Review (not final basemap atlas)')
        c.setAuthor('SC AMP/FSA GIS workflow')
        overview(c,county,subset,boundaries,points,1)
        page=2
        for farm in subset:
            detail_pages=details(c,county,farm,fields,points,boundaries,page)
            page_log.append({'county':county,'farm_id':farm['farm_id'] if not farm.get('missing_id') else '',
                             'unresolved_producer_id':farm.get('producer_ref',''),
                             'map_number':farm['number'],'pdf':str(filename.relative_to(OUT)),
                             'detail_pages':';'.join(map(str,detail_pages)),'source_insets':1 if farm.get('registered_field_geometry') else len(farm['source_matches']),
                             'satellite_pdf_generated':False,'topographic_pdf_generated':False,
                             'status':'SOURCE_REVIEW_ONLY'})
            page+=len(detail_pages)
        c.save()
        doc=pymupdf.open(filename)
        assert len(doc)==page-1
        county_log.append({'county':county,'listed_farm_ids':sum(not f.get('missing_id') for f in subset),
                           'unresolved_enrollment_records':sum(f.get('missing_id',False) for f in subset),
                           'overview_index_entries':len(subset),'detail_inventory_entries':len(subset),
                           'review_pdf_pages':len(doc),'review_pdf':str(filename.relative_to(OUT)),
                           'satellite_pdf_status':'NOT_GENERATED_BASEMAP_AND_REGISTRATION_PENDING',
                           'topographic_pdf_status':'NOT_GENERATED_BASEMAP_AND_REGISTRATION_PENDING'})
        print(county,'entries',len(subset),'pages',len(doc),flush=True)
    for filename,rows in [('map_generation_log.csv',page_log),('county_pdf_verification.csv',county_log)]:
        with (OUT/'qa'/filename).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print('Source review PDFs',len(county_log),'total pages',sum(r['review_pdf_pages'] for r in county_log),flush=True)


if __name__=='__main__':
    main()
