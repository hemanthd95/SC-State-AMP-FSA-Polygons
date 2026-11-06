"""Produce honest county map atlases and field-review sheets for the Nov 6 batch.

Only FSA fields with a non-degenerate image registration become GeoJSON
polygons. Other FSA scans appear in an explicitly labeled review appendix.
"""
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
import csv
import json
import zipfile

import fitz
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
import requests
from shapely.geometry import Point, mapping, shape

from build_three_county_atlases import pixels_to_ll
import build_verified_atlases as atlas
from build_verified_atlases import (W,H,GEOD, NAVY, GRAY, PALETTE, common,
    draw_county, draw_detail, fetch_image, fixed_bbox, frame_img, coord_box,
    rings, draw_shape, bar_and_north, font, wrap, example_qgis_polygon)

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source_recovered/unpacked/SC State_AMP_FSA MAP'
atlas.SOURCE=SRC
ANALYSIS=ROOT/'analysis/allendale_bamberg_calhoun_20261106'
OUT=ROOT/'delivery/allendale_bamberg_calhoun_20261106'
GEO=ROOT/'geojson/counties'
OUT.mkdir(parents=True,exist_ok=True)
GEO.mkdir(parents=True,exist_ok=True)

COUNTIES=('Allendale','Bamberg','Calhoun')
FIPS={'Allendale':'45005','Bamberg':'45009','Calhoun':'45017',
      'Hampton':'45049','Orangeburg':'45075','Lexington':'45063'}

PENDING={
 'Allendale':[
  dict(id='10333',name='Samuel Lance Jr.',tract='2161',field='2161',
       pdf='Samuel Lance JR.pdf', page=1,
       status='FSA HAMPTON / ID CONFLICT',
       note='FSA map shows Hampton Farm 3740 / Tract 10333, not workbook Farm 10333 / Tract 2161. No usable farm GPS.'),
  dict(id='3779',name='Tiffany Loadholt',tract='10394',field='54',
       pdf='Tifanny Loadholt_FSA_Map.pdf',page=1,
       status='FSA HAMPTON / NEEDS PLACEMENT',
       note='FSA confirms Farm 3779 / Tract 10394 / Field 54 but labels Hampton County. Workbook GPS is not a verified field location.'),
 ],
 'Bamberg':[
  dict(id='3524',name='John Brabham',tract='3531',field='25',
       pdf='John Henry Brabham_FSA_Map.pdf',page=2,
       status='FSA VERIFIED / NEEDS PLACEMENT',
       note='Correct alternate source located: Farm 3524 / Tract 3531 / Field 25. Supplied GPS does not align with this FSA map; needs QGIS field placement.'),
 ],
 'Calhoun':[
  dict(id='3549',name='Jan Boneparte',tract='8353',field='2',
       pdf='Jan Davis-Boneparte_FSA_Map.pdf',page=1,
       status='FSA VERIFIED / NEEDS PLACEMENT',
       note='FSA confirms Calhoun Farm 3549 / Tract 8353 / Field 2. Supplied GPS does not align; requires QGIS georeferencing.'),
  dict(id='14280',name='Jaylon Carson',tract='46258',field='3',
       pdf='Jaylon carson_FSA Map.pdf',page=2,
       status='FSA ORANGEBURG / REASSIGN TO REVIEW',
       note='FSA is Orangeburg Farm 14280 / Tract 46258 / Field 3, not Calhoun. No verified geographic polygon; tracked for Orangeburg review.'),
 ],
}


def boundaries():
    cache=ROOT/'geojson/allendale_bamberg_calhoun_source_county_boundaries.geojson'
    if not cache.exists():
        service='https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1/query'
        filters=','.join("'"+v+"'" for v in FIPS.values())
        res=requests.get(service,params={'where':f'GEOID IN ({filters})',
          'outFields':'GEOID,NAME','outSR':'4326','f':'geojson'},timeout=50)
        res.raise_for_status()
        response=res.json()
        features=[f for f in response['features'] if f['properties'].get('GEOID') in set(FIPS.values())]
        if len(features)!=len(FIPS):raise ValueError(f'Census boundaries missing: {len(features)}')
        cache.write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2)+'\n')
    source=json.loads(cache.read_text())
    out={}
    for n,fips in FIPS.items():
        out[n]=shape(next(f['geometry'] for f in source['features'] if f['properties']['GEOID']==fips))
    return out,cache


def point_audit(bound):
    points={
      '3779':(-81.3224192,33.0084896),
      '3523':(-81.0501333,33.2387299),
      '3524':(-81.6563,33.7577),
      '3549':(-81.658,33.7591),
      '14280':(-80.4521,33.6101),
    }
    return {fid:next((n for n,polygon in bound.items() if polygon.covers(Point(*xy))),
                'OUTSIDE_TEST_COUNTIES') for fid,xy in points.items()}


def bamberg_fsa_feature(bound):
    rec=next(r for r in json.loads((ANALYSIS/'registration_results.json').read_text())
             if r.get('farm_id')=='3523')
    assert rec['status']=='POTENTIAL_REGISTRATION_NEEDS_FIELD_TRACE'
    assert rec['registration']['inliers']>=75 and .2<rec['registration']['rmse_px']<3
    # Manually traced yellow FSA field-29 perimeter in the 1102x1426 source raster.
    # Coordinates divided by the PDF rasterization scale before homography.
    ring=[(648,431),(807,573),(580,870),(466,814),(438,710),(415,665)]
    geom=pixels_to_ll([(x/rec['source_render_scale'],y/rec['source_render_scale']) for x,y in ring],rec)
    if not geom.is_valid or not bound['Bamberg'].covers(geom.representative_point()):
        raise ValueError('Farm 3523 polygon failed Bamberg county boundary check')
    acres=abs(GEOD.geometry_area_perimeter(geom)[0])/4046.8564224
    if abs(acres/11.85-1)>.09:raise ValueError(f'Farm 3523 FSA area mismatch: {acres}')
    return {'type':'Feature','geometry':mapping(geom),'properties':{
        'county':'Bamberg','amp_roster_county':'Bamberg',
        'county_workbook_selected':True,'farm_id':'3523','tract_id':'3532',
        'field_id':'29','producer':'Corey Cosby',
        'fsa_reported_acres':11.85,'calculated_acres':round(acres,2),
        'source_pdf':rec['source_pdf'],'source_page':1,
        'method':'FSA raster field traced and aligned to USGS NAIP aerial imagery',
        'image_registration_inliers':rec['registration']['inliers'],
        'registration_rmse_pixels':rec['registration']['rmse_px'],
        'status':'FSA_RASTER_ALIGNED_APPROXIMATE_NOT_SURVEY',
        'registration_date':'2026-11-06'}}


def empty_county_overview(c,county,basetype,boundary,pending,point_countries):
    frame=(39,117,853,532)
    pts=[xy for ring in rings(boundary) for xy in ring]
    bounds=fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.10)
    im,source=fetch_image(bounds,1706,1064,basetype)
    common(c,county,basetype,'01 / County overview / FSA farm review status',1,source)
    frame_img(c,im,frame);cvt=coord_box(bounds,frame)
    draw_shape(c,boundary,cvt,colors.white,width=4)
    draw_shape(c,boundary,cvt,NAVY,width=1.5)
    bar_and_north(c,bounds,frame)
    font(c,922,619,'FARM SOURCE AUDIT',13,NAVY,True)
    font(c,922,591,'0 independently mapped fields',11,colors.HexColor('#A34A24'),True)
    y=551
    for ix,row in enumerate(pending,1):
        font(c,922,y,f'{ix:02d}  FARM {row["id"]}',12,NAVY,True);y-=21
        y=wrap(c,row['name'],922,y,260,10,14)-8
        y=wrap(c,row['status'],922,y,260,9,13,colors.HexColor('#A34A24'))-27
    y=wrap(c,'No FSA polygon is drawn here until its location can be aligned reliably with the printed source map.',922,max(y,270),255,10,15,GRAY)-14
    if county=='Allendale':
        wrap(c,'A separate older QGIS example shows one combined area, but it does not establish two independent farm fields.',922,y,260,9,14,GRAY)
    c.showPage()


def review_appendix(c,county,basetype,entry,page_num):
    src=SRC/entry['pdf']
    with fitz.open(src) as doc:
        pix=doc[entry['page']-1].get_pixmap(matrix=fitz.Matrix(1.35,1.35),colorspace=fitz.csRGB,alpha=False)
        img=Image.open(BytesIO(pix.tobytes('png')))
    common(c,county,basetype,f'{page_num:02d} / FSA source sheet / requires QGIS placement',page_num,'Original USDA FSA page')
    box=(39,118,770,534)
    iw,ih=img.size
    scale=min(box[2]/iw,box[3]/ih)
    x=box[0]+(box[2]-iw*scale)/2
    y=box[1]+(box[3]-ih*scale)/2
    c.drawImage(ImageReader(img),x,y,width=iw*scale,height=ih*scale,mask='auto')
    font(c,839,620,f'FARM {entry["id"]}',16,NAVY,True)
    y=wrap(c,entry['name'],839,597,330,12,18)-19
    font(c,839,y,f'Tract {entry["tract"]}   |   Field {entry["field"]}',11,NAVY,True);y-=36
    y=wrap(c,entry['status'],839,y,330,11,16,colors.HexColor('#A34A24'))-27
    y=wrap(c,entry['note'],839,y,330,10,16,GRAY)-25
    wrap(c,'Source page included for visual matching in QGIS. It is not a georeferenced farm polygon, and is not displayed as a verified field on the county overview.',839,y,325,10,16,GRAY)
    c.showPage()


def extra_reviewer_page(c,basetype,page_num):
    geom,acres=example_qgis_polygon()
    frame=(39,118,853,531)
    bounds=fixed_bbox(list(geom.exterior.coords),frame[2]/frame[3],pad_fraction=.38,min_m=500)
    im,label=fetch_image(bounds,1706,1064,basetype)
    common(c,'Allendale',basetype,f'{page_num:02d} / Existing QGIS example / NOT a farm-verified field',page_num,label)
    frame_img(c,im,frame);cvt=coord_box(bounds,frame)
    draw_shape(c,geom,cvt,colors.HexColor('#AC4E9E'),width=3.0,fillalpha=.20)
    bar_and_north(c,bounds,frame)
    font(c,921,618,'QGIS EXAMPLE',13,NAVY,True)
    y=wrap(c,'Previously supplied georeferenced combined area',921,583,256,11,17)-23
    y=wrap(c,f'Approximate digitized area: {acres:.1f} acres.',921,y,256,10,15)-20
    wrap(c,'This combined shape cannot be allocated to the separate Samuel Lance Jr. and Tiffany Loadholt FSA fields. Their source maps say Hampton County; field-level confirmation is pending.',921,y,256,10,16,GRAY)
    c.showPage()


def render(county,kind,feature,bounds):
    outfile=OUT/f'{county}_County_{kind}_FSA_Atlas_20261106.pdf'
    if outfile.exists():
        with fitz.open(outfile) as prev:
            if len(prev)==3 and prev[0].get_images():
                print('REUSE_VALIDATED',county,kind,flush=True)
                return outfile
    doc=canvas.Canvas(str(outfile),pagesize=(W,H),pageCompression=1)
    doc.setTitle(f'{county} County / {kind} / FSA field atlas and source review')
    farm={str(feature['properties']['farm_id']):[feature]} if county=='Bamberg' else {}
    if farm:
        draw_county(doc,county,farm,bounds[county],kind,set())
        draw_detail(doc,county,farm,'3523',[feature],kind,2,set())
        n=3
    else:
        empty_county_overview(doc,county,kind,bounds[county],PENDING[county],None)
        n=2
    for review in PENDING[county]:
        review_appendix(doc,county,kind,review,n);n+=1
    if county=='Allendale':
        extra_reviewer_page(doc,kind,n);n+=1
    doc.save()
    with fitz.open(outfile) as pdf:
        if len(pdf)!=n-1 or not pdf[0].get_images():
            raise ValueError('PDF validation failed: '+str(outfile))
        if county=='Bamberg' and '3523' not in pdf[1].get_text():
            raise ValueError('Mapped Bamberg field missing in PDF')
    print('ATLAS_READY',county,kind,'pages',n-1,'bytes',outfile.stat().st_size,flush=True)
    return outfile


def main():
    bound,county_file=boundaries()
    hints=point_audit(bound)
    print('SPREADSHEET_POINT_COUNTIES',hints,flush=True)
    f=bamberg_fsa_feature(bound)
    print('VERIFIED',f['properties']['producer'],'Farm 3523 Field 29',f['properties']['calculated_acres'],'ac',flush=True)
    polygonfile=GEO/'bamberg_farm_3523_field_29_fsa_georeg_20261106.geojson'
    polygonfile.write_text(json.dumps({'type':'FeatureCollection','features':[f]},indent=2)+'\n')
    rows=[]
    for county in COUNTIES:
        for p in PENDING[county]:
            rows.append(dict(amp_county=county,farm_id=p['id'],producer=p['name'],tract_id=p['tract'],
               selected_field_id=p['field'],source_fsa_county=('Hampton' if county=='Allendale' else
                 'Orangeburg' if p['id']=='14280' else county),
               spreadsheet_point_in_county=hints.get(p['id'],'no valid GPS'),
               source_pdf=p['pdf'],status=p['status'],note=p['note']))
    rows.append(dict(amp_county='Bamberg',farm_id='3523',producer='Corey Cosby',tract_id='3532',
       selected_field_id='29',source_fsa_county='Bamberg',spreadsheet_point_in_county=hints.get('3523'),
       source_pdf=f['properties']['source_pdf'],status='GEOREFERENCED_FSA_FIELD_COMPLETE',
       note='Selected field georeferenced using 89 nondegenerate aerial-image matches; approx 12 acres.'))
    rows=sorted(rows,key=lambda r:(r['amp_county'],r['farm_id']))
    audit=OUT/'Farm_FSA_Source_And_County_Audit.csv'
    with audit.open('w',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    dest=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(render,county,kind,f,bound):(county,kind)
              for county in COUNTIES for kind in ('Satellite','Topography')}
        for future in as_completed(jobs):dest.append(future.result())
    readme=OUT/'READ_FIRST.txt'
    readme.write_text('ALLENDALE / BAMBERG / CALHOUN FSA COUNTY BATCH  -  6 NOV 2026\n\n'
        'This is an evidence-first partial atlas, NOT a claim that every farm has been mapped.\n'
        'BAMBERG: Corey Cosby Farm 3523 Tract 3532 Field 29 has an aligned polygon. John Brabham Farm 3524 / Tract 3531 / Field 25 has the correct source PDF but does not yet have a geographic alignment.\n'
        'ALLENDALE: two roster entries; both FSA sheets say Hampton County. Samuel Lance Jr. also has a Farm/Tract ID conflict. Included user QGIS combined example is NOT two verified farm fields.\n'
        'CALHOUN: Jan Boneparte Farm 3549 is FSA-correct but GPS not matched. Jaylon Carson Farm 14280 / Tract 46258 / Field 3 is explicitly labeled Orangeburg on the FSA source; awaits polygon registration under Orangeburg.\n'
        'Each PDF begins with a county boundary overview. A mapped field has a numbered marker and polygon close-up; unplaced FSA scans appear as source review sheets with clear warnings.\n'
        'Private source PDFs / geospatial data must remain under authorized access; geographic drawings are not legal surveys.\n')
    bundle=OUT/'Allendale_Bamberg_Calhoun_FSA_Atlases_and_GeoJSON_20261106.zip'
    with zipfile.ZipFile(bundle,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for path in dest+[audit,readme,polygonfile,county_file]:
            z.write(path,path.name)
    print('PACKAGE',bundle,'bytes',bundle.stat().st_size,flush=True)

if __name__=='__main__':main()
