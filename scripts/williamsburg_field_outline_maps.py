"""Extract actual GeoPDF field paths and build new GIS map frames for two farms."""
import csv
import hashlib
import json
import math
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED

import pymupdf
from openpyxl import load_workbook
from PIL import Image
from pyproj import Geod,Transformer
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from shapely.geometry import Polygon,Point,shape,mapping,MultiPolygon
from shapely import union_all

from atlas_geopdf import georef
from atlas_review_pdfs import county_map,paragraph,text,NAVY,GRAY
from atlas_export_gis import shape_export
import shapefile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT=ROOT/'outputs/field_outline_maps/Williamsburg'
WORK=Path('/workspace/amp-atlas-work/williamsburg_fresh_gis')
to_utm=Transformer.from_crs(4326,32617,always_xy=True)
geod=Geod(ellps='WGS84')


def collection(path,features):path.write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2))


def page_header(c,subtitle,page):
    c.setFillColor(NAVY);c.rect(0,780,1224,12,fill=1,stroke=0)
    text(c,36,750,'SOUTH CAROLINA AMP / FSA',11,bold=True)
    text(c,36,715,'Williamsburg County',27,bold=True)
    text(c,36,691,subtitle,12,GRAY)
    c.setStrokeColor(colors.HexColor('#CFD8DE'));c.line(36,678,1188,678)
    text(c,36,45,'PRIVATE  |  FSA PDF field boundaries and imagery  |  County workbook roster  |  2026-11-03',9,GRAY)
    text(c,36,28,'Administrative map interpretation; not a legal survey. Imagery acquisition date is not provided in the sources.',8,GRAY)
    c.setFillColor(GRAY);c.setFont('Helvetica',9);c.drawRightString(1188,45,f'Page {page}')


def main():
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    book=SOURCE/'Producers by County/Williamsburg County_Producers.xlsx'
    w=load_workbook(book,read_only=True,data_only=True)
    roster=[]
    for rownum,row in enumerate(w.active.iter_rows(max_col=9,values_only=True),1):
        if rownum>1 and row[2] is not None:
            roster.append({'number':len(roster)+1,'farm_id':str(row[2]),'tract_id':str(row[3]),'excel_field_id':str(row[4]),'excel_row':rownum,'county':'Williamsburg'})
    assert [(r['farm_id'],r['tract_id']) for r in roster]==[('17615','5419'),('10519','3979')]
    palette=[(.72,.20,.13),(.13,.36,.64)]
    for f,color in zip(roster,palette):f['color']=color
    # Existing source manifest supplies only the already checked path/label
    # associations. Geometry is freshly extracted below from the actual PDFs.
    manifest=json.loads((ROOT/'geojson/master_fsa_fields_geopdf_verified.geojson').read_text())['features']
    fields=[];qa=[]
    for farm in roster:
        records=[f['properties'] for f in manifest if f['properties']['county']=='Williamsburg' and str(f['properties']['farm_id'])==farm['farm_id']]
        assert len(records)==(7 if farm['farm_id']=='17615' else 2)
        source=SOURCE/records[0]['source_pdf'];digest=hashlib.sha256(source.read_bytes()).hexdigest()
        d=pymupdf.open(source);page=d[0];project,residual=georef(d,page);drawings=page.get_drawings();pdftext=page.get_text()
        assert re.search(r'Farm\s*:?\s*'+farm['farm_id']+r'\b',pdftext,re.I)
        assert re.search(r'Tract\s*:?\s*'+farm['tract_id']+r'\b',pdftext,re.I)
        for p in records:
            assert digest==p['source_sha256']
            draw=drawings[p['source_draw_index']];items=draw['items']
            assert all(i[0]=='l' for i in items)
            assert all(items[i-1][2]==items[i][1] for i in range(1,len(items)))
            vertices=[tuple(items[0][1])]+[tuple(i[2]) for i in items]
            assert vertices[0]==vertices[-1], 'Only actual closed source paths are admitted'
            polygon=Polygon(project(vertices));assert polygon.is_valid
            acres=abs(geod.geometry_area_perimeter(polygon)[0])/4046.8564224
            difference=100*(acres-float(p['fsa_reported_acres']))/float(p['fsa_reported_acres'])
            assert abs(difference)<1
            ap=re.escape(f"{float(p['fsa_reported_acres']):g}").replace(r'\.',r'\.\s*')
            assert re.search(r'(?<![\d.])'+str(p['field_id'])+r'\s+'+ap+r'0*(?![\d.])',pdftext)
            properties={k:p[k] for k in ['county','farm_id','tract_id','field_id','fsa_reported_acres','source_pdf','source_sha256','source_draw_index']}
            properties.update(calculated_acres=acres,area_difference_percent=difference,
                              listed_field_in_county_workbook=str(p['field_id'])==farm['excel_field_id'],
                              method='Actual closed vector path from source GeoPDF; GPTS/LPTS affine transformation',
                              crs='EPSG:4326',affine_corner_fit_residual_m=residual)
            fields.append({'type':'Feature','properties':properties,'geometry':mapping(polygon)})
            qa.append({'farm_id':farm['farm_id'],'tract_id':farm['tract_id'],'field_id':p['field_id'],
                       'source_pdf':p['source_pdf'],'drawing_index':p['source_draw_index'],
                       'source_hash_matches':True,'source_path_closed':True,'geometry_valid':True,
                       'printed_field_acreage_pair_found':True,'printed_fsa_acres':p['fsa_reported_acres'],
                       'calculated_acres':acres,'difference_percent':difference,'corner_fit_residual_m':residual})
        farm['source_pdf']=source.name
        cache=WORK/farm['farm_id']
        cache.mkdir(parents=True,exist_ok=True)
        raw_bbox=list(map(float,re.search(r'/BBox\s*\[([^]]+)\]',d.xref_get_key(page.xref,'VP')[1]).group(1).split()))
        viewport=cache/'viewport.json'
        viewport.write_text(json.dumps({'page_width':page.rect.width,'page_height':page.rect.height,
            'bbox_page':[min(raw_bbox[0],raw_bbox[2]),page.rect.height-max(raw_bbox[1],raw_bbox[3]),
                         max(raw_bbox[0],raw_bbox[2]),page.rect.height-min(raw_bbox[1],raw_bbox[3])]}))
        subprocess.run(['/usr/bin/python3',str(ROOT/'scripts/pdf_imagery_raster.py'),str(source),str(cache),'--viewport',str(viewport)],check=True)
        farm['raster_cache']=str(cache)
    assert len(fields)==9
    collection(OUT/'Williamsburg_Extracted_PDF_Field_Outlines.geojson',fields)
    shape_export(OUT/'Williamsburg_Extracted_PDF_Field_Outlines',fields,shapefile.POLYGON)
    farm_features=[];points={}
    for farm in roster:
        group=[f for f in fields if f['properties']['farm_id']==farm['farm_id']]
        geom=union_all([shape(f['geometry']) for f in group]);assert geom.is_valid
        if geom.geom_type=='Polygon':geom=MultiPolygon([geom])
        farm_features.append({'type':'Feature','geometry':mapping(geom),'properties':{
            'county':'Williamsburg','farm_id':farm['farm_id'],'tract_id':farm['tract_id'],
            'source_field_count':len(group),'excel_listed_field_id':farm['excel_field_id']}})
        chosen=next(f for f in group if f['properties']['field_id']==farm['excel_field_id'])
        point=shape(chosen['geometry']).representative_point()
        points[('Williamsburg',farm['farm_id'])]={'type':'Feature','geometry':mapping(point),'properties':{
            'farm_id':farm['farm_id'],'location_status':'REGISTERED_SOURCE_FIELD_REPRESENTATIVE_POINT'}}
    collection(OUT/'Williamsburg_Two_Farms.geojson',farm_features)
    collection(OUT/'Williamsburg_Two_Farm_Locations.geojson',list(points.values()))
    with (OUT/'PDF_Outline_Extraction_QA.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(qa[0]));writer.writeheader();writer.writerows(qa)
    county_data=json.loads((ROOT/'outputs/geojson/SC_County_Boundaries_Census_2022.geojson').read_text())['features']
    boundaries={f['properties']['NAME']:shape(f['geometry']) for f in county_data}
    pdf=OUT/'Williamsburg_Extracted_Field_Outline_Atlas.pdf';c=canvas.Canvas(str(pdf),pagesize=(1224,792),pageCompression=1)
    c.setTitle('Williamsburg County — Two Farms / Nine PDF Field Outlines')
    page_header(c,'FIELD OUTLINE ATLAS  |  2 county-workbook farms  |  9 fields extracted from their FSA PDFs',1)
    county_map(c,'Williamsburg',roster,boundaries,points,(36,125,752,535))
    text(c,815,630,'TWO FARMS FROM THE COUNTY SHEET',13,bold=True)
    y=594
    for farm in roster:
        count=sum(f['properties']['farm_id']==farm['farm_id'] for f in fields)
        text(c,815,y,f"{farm['number']:02d}  Farm {farm['farm_id']}",15,colors.Color(*farm['color']),True)
        y=paragraph(c,f"Tract {farm['tract_id']} | {count} source-PDF fields | Excel row {farm['excel_row']}",815,y-24,350,11)-18
        y=paragraph(c,f"Field listed in Excel: {farm['excel_field_id']}",815,y,350,11)-30
    paragraph(c,'The two farm IDs come only from Williamsburg County_Producers.xlsx, Sheet1 rows 2 and 3. Printed PDF field IDs are field subdivisions, not additional farms.',815,y,350,11)
    text(c,36,101,'County overview: Census county boundary. Farm detail maps: extracted georeferenced PDF imagery with independently drawn vector outlines.',9,GRAY)
    c.showPage()
    for farm in roster:
        group=sorted([f for f in fields if f['properties']['farm_id']==farm['farm_id']],key=lambda f:int(f['properties']['field_id']))
        cache=Path(farm['raster_cache']);ref=json.loads((cache/'imagery_reference.json').read_text())
        xmin,ymin,xmax,ymax=ref['bounds']
        im=Image.open(cache/'imagery.png');image_ratio=im.width/im.height
        frame=(36,130,735,510);x,y,w,h=frame
        iw=min(w,h*image_ratio);ih=iw/image_ratio;ix=x+(w-iw)/2;iy=y+(h-ih)/2
        convert=lambda e,n:(ix+(e-xmin)/(xmax-xmin)*iw,iy+(n-ymin)/(ymax-ymin)*ih)
        page_header(c,f"{farm['number']:02d} / Farm {farm['farm_id']} / Tract {farm['tract_id']} / {len(group)} source fields",farm['number']+1)
        c.drawImage(str(cache/'imagery.png'),ix,iy,width=iw,height=ih,mask='auto')
        placed=[]
        for feature in group:
            p=feature['properties'];geom=shape(feature['geometry']);ring=list(geom.exterior.coords)
            path=c.beginPath()
            for i,lonlat in enumerate(ring):
                px,py=convert(*to_utm.transform(*lonlat))
                if i==0:path.moveTo(px,py)
                else:path.lineTo(px,py)
            path.close()
            c.saveState();c.setFillColor(colors.Color(*farm['color']));c.setFillAlpha(.16)
            c.setStrokeColor(colors.Color(*farm['color']));c.setLineWidth(2.2 if p['listed_field_in_county_workbook'] else 1.3)
            c.drawPath(path,stroke=1,fill=1);c.restoreState()
            rp=geom.representative_point();px,py=convert(*to_utm.transform(rp.x,rp.y))
            lx,ly=px,py
            for attempt in range(60):
                if all(math.hypot(lx-a,ly-b)>22 for a,b in placed):break
                angle=attempt*2.399;radius=12+attempt*.9
                lx=max(ix+12,min(ix+iw-12,px+radius*math.cos(angle)));ly=max(iy+12,min(iy+ih-12,py+radius*math.sin(angle)))
            placed.append((lx,ly))
            c.setStrokeColor(colors.white);c.setLineWidth(1);c.line(px,py,lx,ly)
            label=str(p['field_id']);c.setFillColor(colors.white);c.circle(lx,ly,8,fill=1,stroke=0)
            c.setFillColor(NAVY);c.setFont('Helvetica-Bold',9);c.drawCentredString(lx,ly-3,label)
        sx,sy=ix+15,iy+16
        points_per_metre=iw/(xmax-xmin)
        unit=max(v for v in [1,2,5,10,20,50,100,200,500,1000] if v*points_per_metre<iw*.25)
        c.setFillColor(colors.white);c.rect(sx-5,sy-5,unit*points_per_metre+15,30,fill=1,stroke=0)
        c.setFillColor(NAVY);c.rect(sx,sy,unit*points_per_metre,4,fill=1,stroke=0);text(c,sx,sy+12,f'{unit:g} m',8)
        source_union=shape(next(f['geometry'] for f in farm_features if f['properties']['farm_id']==farm['farm_id']))
        rp=source_union.representative_point();a=to_utm.transform(rp.x,rp.y);b=to_utm.transform(rp.x,rp.y+.001)
        angle=math.atan2(b[1]-a[1],b[0]-a[0]);nx,ny=ix+iw-25,iy+ih-45
        c.setFillColor(colors.white);c.rect(nx-13,ny-8,32,51,fill=1,stroke=0)
        c.setStrokeColor(NAVY);c.setLineWidth(1.5);c.line(nx,ny,nx+24*math.cos(angle),ny+24*math.sin(angle));text(c,nx-4,ny+30,'N',9,bold=True)
        yy=613;text(c,810,yy,'PDF FIELD OUTLINES',14,bold=True);yy-=30
        text(c,810,yy,'Field     Printed acres     Calculated acres',10,bold=True);yy-=24
        for feature in group:
            p=feature['properties'];mark='*' if p['listed_field_in_county_workbook'] else ''
            text(c,810,yy,f"{p['field_id']}{mark:2}          {float(p['fsa_reported_acres']):7.2f}                 {p['calculated_acres']:7.3f}",11)
            yy-=23
        yy=paragraph(c,'* Field ID listed in the county workbook. All other outlined fields are printed in the same FSA farm map; no additional farm records are created.',810,yy-14,365,10)-18
        yy=paragraph(c,'Boundary source: '+farm['source_pdf'],810,yy,365,11)-18
        paragraph(c,'Background: imagery extracted from this PDF with its text and vector layers disabled. Field outlines and labels on this page are newly drawn GIS vectors from the source paths. Image acquisition date is unavailable.',810,yy,365,10,GRAY)
        text(c,36,94,'Source field geometries are retained without buffers or generalized replacement boundaries. Internal GeoPDF reference checks are not survey accuracy.',9,GRAY)
        c.showPage()
    c.save()
    doc=pymupdf.open(pdf);assert len(doc)==3
    assert all('Farm '+f['farm_id'] in doc[0].get_text() for f in roster)
    assert all('Farm '+f['farm_id'] in doc[f['number']].get_text() for f in roster)
    for i,page in enumerate(doc,1):
        assert all(b[0]>=-1 and b[1]>=-1 and b[2]<=1225 and b[3]<=793 for b in page.get_text('blocks') if b[6]==0)
        page.get_pixmap(dpi=100,alpha=False).save(OUT/f'page_{i:02d}.jpg',jpg_quality=85)
    report={'farm_roster_source':book.name,'excel_rows':[2,3],'farm_ids':[f['farm_id'] for f in roster],
            'farm_count':2,'source_pdf_field_count':9,'overview_markers':2,'pdf_pages':3,
            'field_geometries_freshly_extracted_from_source_paths':True,'imagery_only_pdf_rendering':True,
            'max_area_difference_percent':max(abs(r['difference_percent']) for r in qa),
            'crs_geojson':'EPSG:4326','crs_processing':'EPSG:32617',
            'county_overview_background':'Census county boundary; no county-wide aerial mosaic available',
            'topographic_version':'NOT_GENERATED; authoritative USGS service access remains blocked'}
    (OUT/'Verification.json').write_text(json.dumps(report,indent=2))
    (OUT/'README.md').write_text('''# Williamsburg extracted-field GIS maps

Farm roster: exactly two records from Williamsburg County_Producers.xlsx, rows 2 and 3: Farm 17615 / Tract 5419 and Farm 10519 / Tract 3979.

The actual PDFs contain seven field outlines for Farm 17615 and two for Farm 10519. All nine closed paths were freshly extracted from the PDFs, matched to printed field IDs and acreage, transformed using their GeoPDF geographic metadata, and exported to GeoJSON/Shapefile. The field IDs listed in Excel are separately flagged; other source fields do not create additional farms or assumed enrollment records.

The three-page atlas has a two-marker county overview and one GIS detail map per farm. Detail backgrounds contain only the georeferenced imagery extracted from the PDFs. Original PDF vector lines and text were disabled for background rendering; the map outlines, field labels, north arrows, scale bars and acreage tables were newly drawn from the extracted GIS data.

The county overview uses a Census boundary, not county-wide satellite imagery. The USGS topographic version remains unavailable because its service is blocked by the cloud network proxy. No topographic image is synthesized from aerial imagery.
''')
    archive=OUT/'Williamsburg_Extracted_Field_Maps_and_GIS.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for p in sorted(OUT.iterdir()):
            if p.is_file() and p!=archive:z.write(p,p.name)
    with ZipFile(archive) as z:assert z.testzip() is None
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
