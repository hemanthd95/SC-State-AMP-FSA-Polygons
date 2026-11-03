"""Map only the two Williamsburg county-workbook farms; audit other rows separately."""
import csv
import hashlib
import json
import math
import re
import shutil
from zipfile import ZipFile, ZIP_DEFLATED
from pathlib import Path

import pymupdf
from openpyxl import load_workbook
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from shapely.geometry import mapping, shape

from atlas_review_pdfs import county_map, header, paragraph, text, NAVY, GRAY, GOLD
from atlas_export_gis import shape_export
import shapefile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/corrected_county_atlases/Williamsburg'
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
WORK=Path('/workspace/amp-atlas-work')
PDFNAME='Williamsburg_County_Two_Farm_Source_Imagery_Atlas.pdf'


def write_geo(path,features):
    path.write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    workbook_path=SOURCE/'Producers by County/Williamsburg County_Producers.xlsx'
    workbook=load_workbook(workbook_path,read_only=True,data_only=True)
    rows=[]
    for number,row in enumerate(workbook.active.iter_rows(max_col=9,values_only=True),1):
        if number==1 or row[2] is None:continue
        rows.append({'excel_row':number,'farm_id':str(row[2]),'tract_id':str(row[3]),'field_id':str(row[4])})
    assert [(r['farm_id'],r['tract_id'],r['field_id']) for r in rows]==[('17615','5419','7'),('10519','3979','5')]
    source_fields=json.loads((ROOT/'outputs/geojson/SC_AMP_FSA_All_Farm_Fields.geojson').read_text())['features']
    source_farms=json.loads((ROOT/'outputs/geojson/Registered_Source_Farms.geojson').read_text())['features']
    boundary_data=json.loads((ROOT/'outputs/geojson/SC_County_Boundaries_Census_2022.geojson').read_text())['features']
    boundaries={f['properties']['NAME']:shape(f['geometry']) for f in boundary_data}
    farms=[];selected=[];context=[];points={};farm_geoms=[]
    palette=[(0.72,0.20,0.13),(0.13,0.36,0.64)]
    for index,row in enumerate(rows):
        matches=[f for f in source_fields if f['properties']['county']=='Williamsburg' and
                 all(str(f['properties'][key])==row[key] for key in ('farm_id','tract_id','field_id'))]
        assert len(matches)==1
        field=matches[0];selected.append(field)
        point=shape(field['geometry']).representative_point()
        assert boundaries['Williamsburg'].covers(point)
        points[('Williamsburg',row['farm_id'])]={'type':'Feature','geometry':mapping(point),
            'properties':{'county':'Williamsburg','farm_id':row['farm_id'],'location_status':'REGISTERED_SOURCE_FIELD_REPRESENTATIVE_POINT'}}
        farm={**row,'county':'Williamsburg','number':index+1,'color':palette[index],
              'scopes':['county_workbook'],'source_field':field}
        farms.append(farm)
        source_farm=next(f for f in source_farms if f['properties']['county']=='Williamsburg' and str(f['properties']['farm_id'])==row['farm_id'])
        farm_geoms.append({**source_farm,'properties':{**source_farm['properties'],'county_workbook_selected_field':row['field_id']}})
        for f in source_fields:
            p=f['properties']
            if p['county']=='Williamsburg' and str(p['farm_id'])==row['farm_id']:
                context.append({**f,'properties':{**p,'county_workbook_selected':str(p['field_id'])==row['field_id']}})
    assert len(selected)==2 and len(farms)==2 and len(context)==9
    write_geo(OUT/'Williamsburg_County_Workbook_Selected_Fields.geojson',selected)
    write_geo(OUT/'Williamsburg_Source_Fields_Context.geojson',context)
    write_geo(OUT/'Williamsburg_Two_Farms.geojson',farm_geoms)
    write_geo(OUT/'Williamsburg_Two_Farm_Locations.geojson',list(points.values()))
    shape_export(OUT/'Williamsburg_Selected_Fields',selected,shapefile.POLYGON)
    with (OUT/'Williamsburg_County_Roster.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=['excel_row','farm_id','tract_id','field_id'])
        writer.writeheader();writer.writerows(rows)
    with (OUT/'Williamsburg_Excluded_Master_Records.csv').open('w',newline='') as stream:
        writer=csv.writer(stream)
        writer.writerow(['farm_id','source_workbook','sheet','rows','map_status','reason'])
        writer.writerow(['17614','All_Producer list.xlsx','Producer Enrollment_Year 1','7;8;9','EXCLUDED','Not in Williamsburg County_Producers.xlsx; identity must be reconciled, not treated as an additional farm'])
        writer.writerow(['5611','All_Producer list.xlsx','Producer Enrollment_Year 1','63;64;65','EXCLUDED','Not in Williamsburg County_Producers.xlsx; historical/master-only entry'])
    pdf=OUT/PDFNAME;c=canvas.Canvas(str(pdf),pagesize=(1224,792),pageCompression=1)
    c.setTitle('Williamsburg County - Two County-Workbook Farms - FSA Source Imagery Atlas')
    c.setAuthor('SC AMP/FSA GIS workflow')
    header(c,'Williamsburg','COUNTY WORKBOOK ROSTER  |  Exactly 2 farms, 2 selected fields',1)
    county_map(c,'Williamsburg',farms,boundaries,points,(36,130,752,530))
    text(c,815,630,'COUNTY WORKBOOK — TWO FARMS',13,bold=True)
    yy=595
    for f in farms:
        text(c,815,yy,f"{f['number']:02d}  Farm {f['farm_id']}",14,colors.Color(*f['color']),True)
        yy=paragraph(c,f"Tract {f['tract_id']} / Field {f['field_id']}\nSpreadsheet row {f['excel_row']}",815,yy-24,350,11)-30
    yy=paragraph(c,'Map roster: Williamsburg County_Producers.xlsx, Sheet1, rows 2 and 3 only.',815,yy,350,12)-20
    yy=paragraph(c,'Historical/master-only IDs 17614 and 5611 are excluded. They are not additional farms on this map.',815,yy,350,11)-20
    paragraph(c,'Markers use representative points of the two selected source polygons. No address coordinates or invented locations are used.',815,yy,350,11)
    text(c,36,105,'County overview: Census 2022 county boundary. Detail pages: supplied FSA aerial imagery with selected fields highlighted.',9,GRAY)
    c.showPage()
    detail_sources=[]
    for f in farms:
        p=f['source_field']['properties'];source=SOURCE/p['source_pdf']
        assert hashlib.sha256(source.read_bytes()).hexdigest()==p['source_sha256']
        doc=pymupdf.open(source);page=doc[p['page_number']-1]
        drawing=page.get_drawings()[p['source_draw_index']]
        vertices=[item[1] for item in drawing['items'] if item[0]=='l']
        page.wrap_contents()
        page.draw_polyline(vertices,color=f['color'],fill=f['color'],fill_opacity=.22,width=2,closePath=True)
        vp=doc.xref_get_key(page.xref,'VP')[1]
        bb=list(map(float,re.search(r'/BBox\s*\[([^]]+)\]',vp).group(1).split()))
        clip=pymupdf.Rect(min(bb[0],bb[2]),page.rect.height-max(bb[1],bb[3]),max(bb[0],bb[2]),page.rect.height-min(bb[1],bb[3]))
        image_path=OUT/f"Farm_{f['farm_id']}_Selected_Field.jpg"
        page.get_pixmap(dpi=180,clip=clip,alpha=False).save(image_path,jpg_quality=90)
        header(c,'Williamsburg',f"{f['number']:02d} / Farm {f['farm_id']}  |  Tract {f['tract_id']}  |  County-sheet Field {f['field_id']}",f['number']+1)
        text(c,36,650,'SELECTED FIELD FROM COUNTY WORKBOOK',11,colors.Color(*f['color']),True)
        from PIL import Image
        im=Image.open(image_path);factor=min(720/im.width,500/im.height)
        iw,ih=im.width*factor,im.height*factor;xx=36+(735-iw)/2;yy=130+(510-ih)/2
        c.drawImage(str(image_path),xx,yy,width=iw,height=ih)
        x=805;y=610
        y=paragraph(c,f"Farm {f['farm_id']} / Tract {f['tract_id']} / Field {f['field_id']}",x,y,365,17,colors.Color(*f['color']))-18
        y=paragraph(c,f"Printed FSA acreage: {float(p['fsa_reported_acres']):g} acres",x,y,365,12)-16
        y=paragraph(c,f"Recomputed polygon acreage: {float(p['polygon_calculated_acres']):.3f} acres",x,y,365,11)-18
        y=paragraph(c,'Colored fill and outline: the county-workbook selected field. Other printed fields and boundaries are source context and are not added enrollment records.',x,y,365,11)-18
        y=paragraph(c,'Source: '+p['source_pdf']+f" / page {p['page_number']}",x,y,365,11)-18
        if f['farm_id']=='10519':
            y=paragraph(c,'Field selection conflict: the Year 2 master workbook lists Field 7. This atlas follows county-sheet row 3, which lists Field 5.',x,y,365,11,GOLD)-18
        y=paragraph(c,'Source imagery acquisition date is not independently established. This is supplied FSA aerial imagery, not a newly downloaded basemap.',x,y,365,10,GRAY)-18
        paragraph(c,'GeoPDF reference and source vector/area checks passed. These checks do not establish survey accuracy.',x,y,365,10,GRAY)
        # Scale from GDAL's independent geotransform for the original PDF.
        meta=json.loads((WORK/('gdal_'+p['source_sha256']+'.json')).read_text());gt=meta['geoTransform']
        metres_per_source_point=math.hypot(gt[1],gt[4])*meta['size'][0]/page.rect.width
        points_per_metre=iw/(clip.width*metres_per_source_point)
        possible=[1,2,5,10,20,50,100,200,500,1000]
        distance=max(v for v in possible if v*points_per_metre<iw*.3)
        length=distance*points_per_metre
        c.setFillColor(colors.white);c.rect(xx+10,yy+10,length+22,31,fill=1,stroke=0)
        c.setFillColor(NAVY);c.rect(xx+20,yy+20,length,4,fill=1,stroke=0)
        text(c,xx+20,yy+29,f'{distance:g} m',8)
        text(c,36,91,'FSA source imagery is registered through its original GeoPDF metadata. No topographic layer has been substituted or simulated.',9,GRAY)
        c.showPage();detail_sources.append({'farm_id':f['farm_id'],'tract_id':f['tract_id'],'field_id':f['field_id'],'source_pdf':p['source_pdf']})
    c.save()
    d=pymupdf.open(pdf);assert len(d)==3
    assert all('Farm '+r['farm_id'] in d[0].get_text() for r in rows)
    assert all('Farm '+f['farm_id'] in d[i+1].get_text() for i,f in enumerate(farms))
    assert '17614' not in re.sub(r'Historical/master-only IDs 17614 and 5611 are excluded\.[\s\S]*','',d[0].get_text())
    for i,page in enumerate(d,1):page.get_pixmap(dpi=100,alpha=False).save(OUT/f'page_{i:02d}.jpg',jpg_quality=85)
    report={'map_roster_source':str(workbook_path.relative_to(ROOT)),'workbook_sha256':hashlib.sha256(workbook_path.read_bytes()).hexdigest(),
            'sheet':'Sheet1','spreadsheet_rows':[2,3],'farms_in_county_workbook':2,'overview_marker_count':2,'farm_detail_pages':2,'pdf_page_count':3,
            'included_farm_ids':[r['farm_id'] for r in rows],'excluded_master_only_farm_ids':['17614','5611'],
            'selected_fields':detail_sources,'all_source_context_field_count':9,
            'scope_error_corrected':'Historical/master-only records had been incorrectly added to the county map roster.',
            'topographic_atlas_status':'NOT_GENERATED; USGS service request still blocked by environment proxy',
            'satellite_scope':'Detail pages use actual supplied FSA aerial imagery; overview uses Census boundary, not county-wide satellite imagery.'}
    (OUT/'Williamsburg_Verification.json').write_text(json.dumps(report,indent=2))
    (OUT/'README.md').write_text('''# Williamsburg county-workbook correction

The map roster is exactly the two rows in `Williamsburg County_Producers.xlsx`: Farm 17615 / Tract 5419 / Field 7 (row 2), and Farm 10519 / Tract 3979 / Field 5 (row 3).

The previous four-entry county review incorrectly included Farm 17614 (Year 1 master rows 7–9) and Farm 5611 (Year 1 master rows 63–65). Their IDs came from source records; adding them to this county map without reconciliation was an error. They are excluded here.

- [Corrected three-page source-imagery atlas](Williamsburg_County_Two_Farm_Source_Imagery_Atlas.pdf)
- [Exact county-workbook roster](Williamsburg_County_Roster.csv)
- [Excluded master records and provenance](Williamsburg_Excluded_Master_Records.csv)
- [Verification](Williamsburg_Verification.json)

The two selected field polygons and both farm source boundaries are included as GeoJSON. Nine source fields are retained in the context layer; only Fields 7 and 5 selected above are enrollment selections for this map. Other source field outlines do not represent extra farms or extra enrolled fields.

The imagery on detail pages is the actual supplied FSA aerial imagery, registered through GeoPDF metadata. The overview is a Census county-boundary map. The original request for separate county-wide satellite and USGS topographic backgrounds remains incomplete: external map-service access is still blocked. No topographic background is simulated.
''')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
