"""Preserve Corey's FSA field and add John's user-digitized farm-area outline.

John's approximately 18-acre QGIS area is intentionally NOT relabeled as the
10.20-acre USDA FSA Field 25. The distinction appears on every PDF page.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
import json
import zipfile

import fitz
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from shapely.geometry import shape, mapping

import build_verified_atlases as atlas

ROOT=Path(__file__).resolve().parents[1]
USER=ROOT/'upload/John_Brabham_Farm_Area.geojson'
COREY=ROOT/'geojson/counties/bamberg_farm_3523_field_29_fsa_georeg_20261106.geojson'
BOUNDARIES=ROOT/'geojson/allendale_bamberg_calhoun_source_county_boundaries.geojson'
SOURCE=ROOT/'source_recovered/unpacked/SC State_AMP_FSA MAP'
OUT=ROOT/'delivery/bamberg_john_qgis_update_20261106'
GEO=ROOT/'geojson/counties'
OUT.mkdir(parents=True,exist_ok=True)
GEO.mkdir(parents=True,exist_ok=True)
atlas.SOURCE=SOURCE
COLORS={'3523':colors.HexColor('#F25F4C'),'3524':colors.HexColor('#0795B5')}
NAVY=atlas.NAVY
GRAY=atlas.GRAY
W,H=atlas.W,atlas.H


def load_features():
    corey=json.loads(COREY.read_text())['features'][0]
    donated=json.loads(USER.read_text())
    assert donated['type']=='FeatureCollection' and len(donated['features'])==1
    assert donated['crs']['properties']['name'].endswith('CRS84')
    john_geometry=donated['features'][0]['geometry']
    john=shape(john_geometry)
    corey_shape=shape(corey['geometry'])
    boundary=shape(next(f['geometry'] for f in json.loads(BOUNDARIES.read_text())['features']
                        if f['properties'].get('GEOID')=='45009'))
    assert john.is_valid and john.area>0 and boundary.covers(john.representative_point())
    assert corey_shape.is_valid and boundary.covers(corey_shape.representative_point())
    # A few dozen square meters of user-digitization overlap are retained,
    # not silently erased from the original drawing.
    overlap=abs(atlas.GEOD.geometry_area_perimeter(john.intersection(corey_shape))[0])
    if overlap>200:raise ValueError(f'Unexpected large overlap between farmers: {overlap:.1f} m²')
    if john.distance(corey_shape)>.00015:raise ValueError('QGIS John area is not adjacent to Corey')
    acres=abs(atlas.GEOD.geometry_area_perimeter(john)[0])/4046.8564224
    if not 17<acres<20:raise ValueError('Unexpected area in user QGIS geometry')
    properties={
        'county':'Bamberg','amp_roster_county':'Bamberg',
        'producer':'John Brabham','farm_id':'3524','tract_id':'3531',
        'field_id':None,'target_fsa_field_id':'25',
        'target_fsa_field_acres':10.20,'calculated_area_acres':round(acres,2),
        'geometry_represents':'USER_QGIS_DIGITIZED_APPROXIMATE_FARM_AREA',
        'source_fsa_pdf':'John Henry Brabham_FSA_Map.pdf','source_fsa_page':2,
        'user_source_geojson':USER.name,
        'fsa_field_boundary_verified':False,
        'status':'FARM_AREA_LOCATED__SELECTED_FSA_FIELD25_BOUNDARY_PENDING',
        'source_note':'Whole QGIS area is not claimed to be FSA Field 25; source Field 25 is 10.20 acres.',
        'updated':'2026-11-06'}
    feature={'type':'Feature','properties':properties,'geometry':john_geometry}
    return corey,feature,boundary,acres,overlap


def save_geodata(corey,john):
    combined=GEO/'bamberg_corey_3523_fsa_and_john_3524_qgis_area_20261106.geojson'
    individual=GEO/'john_brabham_farm_3524_qgis_area_not_fsa_field25_20261106.geojson'
    combined.write_text(json.dumps({'type':'FeatureCollection','features':[corey,john]},indent=2)+'\n')
    individual.write_text(json.dumps({'type':'FeatureCollection','features':[john]},indent=2)+'\n')
    return [combined,individual]


def mixed_header(c,basetype,subtitle,page,provider):
    c.setFillColor(NAVY);c.rect(0,H-15,W,15,fill=1,stroke=0)
    atlas.font(c,40,753,'SOUTH CAROLINA STATE UNIVERSITY   /   AMP PROGRAM',11,NAVY,True)
    atlas.font(c,40,719,'Bamberg County',26,NAVY,True)
    atlas.font(c,40,691,subtitle,12,GRAY)
    c.setStrokeColor(colors.HexColor('#D6E0E4'));c.line(40,674,1184,674)
    c.setFillColor(atlas.PALE);c.rect(0,0,W,65,fill=1,stroke=0)
    atlas.font(c,40,45,f'PRIVATE  |  FSA registered field and separate user QGIS review area  |  Basemap: {provider}',9,GRAY)
    atlas.font(c,40,28,'John Brabham QGIS area is NOT the verified FSA Field 25 boundary; field area is approximate, not a survey.',9,GRAY)
    c.setFillColor(GRAY);c.setFont('Helvetica',9)
    c.drawRightString(1185,45,f'{basetype.upper()}  |  {page}')


def county_overview(c,kind,corey,john,boundary):
    frame=(39,117,853,532)
    pts=[v for ring in atlas.rings(boundary) for v in ring]
    bounds=atlas.fixed_bbox(pts,frame[2]/frame[3],pad_fraction=.1)
    img,provider=atlas.fetch_image(bounds,1706,1064,kind)
    mixed_header(c,kind,'01 / County overview / FSA field and QGIS farm location',1,provider)
    atlas.frame_img(c,img,frame);cvt=atlas.coord_box(bounds,frame)
    atlas.draw_shape(c,boundary,cvt,colors.white,width=3.7)
    atlas.draw_shape(c,boundary,cvt,NAVY,width=1.5)
    for fid,feat,offset in [('3523',corey,(-25,25)),('3524',john,(26,-24))]:
        p=shape(feat['geometry']).representative_point()
        ax,ay=cvt(p.x,p.y)
        x,y=ax+offset[0],ay+offset[1]
        c.setStrokeColor(colors.white);c.setLineWidth(3);c.line(ax,ay,x,y)
        c.setStrokeColor(COLORS[fid]);c.setLineWidth(1.7);c.line(ax,ay,x,y)
        c.setFillColor(colors.white);c.circle(x,y,13,stroke=0,fill=1)
        c.setFillColor(COLORS[fid]);c.circle(x,y,10.5,stroke=0,fill=1)
        c.setFont('Helvetica-Bold',10);c.setFillColor(colors.white)
        c.drawCentredString(x,y-3.5,'1' if fid=='3523' else '2')
    atlas.bar_and_north(c,bounds,frame)
    atlas.font(c,920,622,'FARM INDEX',12,NAVY,True)
    c.setFillColor(COLORS['3523']);c.roundRect(922,580,18,18,3,fill=1,stroke=0)
    atlas.font(c,950,585,'01  FARM 3523',12,NAVY,True)
    atlas.font(c,922,554,'Corey Cosby',11,NAVY)
    atlas.wrap(c,'FSA-aligned Field 29  |  11.85 acres (source)',922,532,260,10,15,GRAY)
    c.setFillColor(COLORS['3524']);c.roundRect(922,480,18,18,3,fill=1,stroke=0)
    atlas.font(c,950,485,'02  FARM 3524',12,NAVY,True)
    atlas.font(c,922,454,'John Brabham',11,NAVY)
    y=atlas.wrap(c,'User QGIS-identified farm area  |  18.1 acres approximate',922,432,260,10,15,GRAY)-16
    y=atlas.wrap(c,'FSA Field 25 = 10.20 acres; the selected field perimeter remains unverified.',922,y,260,10,15,colors.HexColor('#A34A24'))-20
    atlas.wrap(c,'Both numbered markers locate their respective polygons; the different mapping statuses are intentional.',922,y,260,9,13,GRAY)
    atlas.font(c,923,124,'County boundary: U.S. Census',8,GRAY)
    c.showPage()


def john_closeup(c,kind,corey,john,acres):
    geom=shape(john['geometry']);neighbor=shape(corey['geometry'])
    frame=(39,119,853,532)
    coords=[v for g in (geom,neighbor) for ring in atlas.rings(g) for v in ring]
    bounds=atlas.fixed_bbox(coords,frame[2]/frame[3],pad_fraction=.21,min_m=670)
    img,provider=atlas.fetch_image(bounds,1706,1064,kind)
    mixed_header(c,kind,'03 / Farm 3524 / User-digitized farm area (FSA Field 25 pending)',3,provider)
    atlas.frame_img(c,img,frame);cvt=atlas.coord_box(bounds,frame)
    atlas.draw_shape(c,neighbor,cvt,COLORS['3523'],width=2.5,fillalpha=.08)
    atlas.draw_shape(c,geom,cvt,COLORS['3524'],width=3.2,fillalpha=.22)
    p=geom.representative_point();x,y=cvt(p.x,p.y)
    c.setFillColor(colors.white);c.roundRect(x-49,y-12,98,24,5,stroke=0,fill=1)
    c.setFont('Helvetica-Bold',10);c.setFillColor(NAVY);c.drawCentredString(x,y-3,'QGIS AREA')
    atlas.bar_and_north(c,bounds,frame)
    atlas.font(c,922,623,'FARM 3524',17,NAVY,True)
    atlas.font(c,922,595,'John Brabham',12,NAVY)
    atlas.font(c,922,556,'USER QGIS FARM AREA',11,COLORS['3524'],True)
    atlas.font(c,922,531,f'Approx. {acres:.1f} acres',11,NAVY,True)
    yy=atlas.wrap(c,'The cyan boundary is your QGIS drawing. It identifies the farm area, not the smaller USDA FSA Field 25.',922,498,260,10,15,GRAY)-19
    atlas.font(c,922,yy,'FSA SELECTED FIELD 25',11,NAVY,True);yy-=19
    atlas.font(c,922,yy,'10.20 acres on source map',10,colors.HexColor('#A34A24'),True);yy-=33
    yy=atlas.wrap(c,'The source map describes Field 25 with handwritten 25A/25B subdivisions. Its exact perimeter is not yet extracted from this larger area.',922,yy,260,10,15,GRAY)-20
    yy=atlas.wrap(c,'Coral outline: Corey Cosby FSA Field 29, shown only as a nearby spatial reference.',922,yy,260,10,15,GRAY)
    atlas.font(c,922,132,'No clipping or boundary adjustments applied to your GeoJSON.',8,GRAY)
    c.showPage()


def source_reference(c,kind):
    path=SOURCE/'John Henry Brabham_FSA_Map.pdf'
    with fitz.open(path) as doc:
        page=doc[1]
        pix=page.get_pixmap(matrix=fitz.Matrix(1.35,1.35),colorspace=fitz.csRGB,alpha=False)
        img=Image.open(BytesIO(pix.tobytes('png')))
    mixed_header(c,kind,'04 / Farm 3524 / FSA source comparison - Field 25',4,'USDA FSA original page')
    frame=(39,118,760,534)
    factor=min(frame[2]/img.width,frame[3]/img.height)
    c.drawImage(ImageReader(img),frame[0]+(frame[2]-img.width*factor)/2,
                frame[1]+(frame[3]-img.height*factor)/2,
                img.width*factor,img.height*factor,mask='auto')
    atlas.font(c,840,623,'SOURCE MAP',15,NAVY,True)
    yy=atlas.wrap(c,'John Brabham / Farm 3524 / Tract 3531',840,593,315,12,17)-24
    atlas.font(c,840,yy,'FSA Field 25: 10.20 acres',11,NAVY,True);yy-=34
    yy=atlas.wrap(c,'The red handwritten notes indicate management subdivisions within Field 25.',840,yy,310,10,15,GRAY)-24
    yy=atlas.wrap(c,'Your georeferenced QGIS shape locates the broader farm area and is preserved unchanged in the next downloadable GeoJSON.',840,yy,310,10,15,GRAY)-24
    atlas.wrap(c,'The FSA map is included for refining the Field 25 perimeter later. It has not been falsely registered to a smaller boundary.',840,yy,310,10,15,colors.HexColor('#A34A24'))
    c.showPage()


def render(kind,corey,john,boundary,acres):
    filename=OUT/f'Bamberg_County_{kind}_Updated_Corey_and_John_20261106.pdf'
    c=canvas.Canvas(str(filename),pagesize=(W,H),pageCompression=1)
    c.setTitle(f'Bamberg County {kind}: Corey FSA field and John QGIS farm area')
    county_overview(c,kind,corey,john,boundary)
    farms={'3523':[corey]}
    atlas.draw_detail(c,'Bamberg',farms,'3523',[corey],kind,2,set())
    john_closeup(c,kind,corey,john,acres)
    source_reference(c,kind)
    c.save()
    with fitz.open(filename) as check:
        assert len(check)==4 and all(page.get_images() for page in check)
        overview=check[0].get_text()
        assert '3523' in overview and '3524' in overview
        assert 'QGIS' in check[2].get_text() and '10.20' in check[2].get_text()
    print('PDF_READY',filename.name,filename.stat().st_size,flush=True)
    return filename


def main():
    corey,john,boundary,acres,overlap=load_features()
    print('GEO_VALIDATED','John',round(acres,2),'ac','Corey overlap',round(overlap,1),'m2',flush=True)
    geodata=save_geodata(corey,john)
    paths=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(render,kind,corey,john,boundary,acres)
              for kind in ('Satellite','Topography')]
        for result in as_completed(jobs):paths.append(result.result())
    note=OUT/'READ_FIRST_Bamberg_20261106.txt'
    note.write_text('BAMBERG COUNTY / UPDATED TWO FARM ATLAS\n'
        'Farm 3523 Corey Cosby: independently image-aligned FSA Field 29, source 11.85 acres.\n'
        f'Farm 3524 John Brabham: user QGIS approximate farm area ({acres:.1f} acres), NOT equivalent to source FSA Field 25 (10.20 acres).\n'
        'Page 1 county outline and two numbered farm markers; page 2 Corey mapped field; page 3 John QGIS area and Corey neighbor; page 4 John original FSA source sheet.\n'
        'The user polygon coordinates were preserved exactly. No invented FSA Field 25 boundary was added.\n'
        f'Slight polygon overlap (~{overlap:.0f} m2) is user-digitization tolerance and was not silently clipped.\n')
    bundle=OUT/'Bamberg_County_Updated_Corey_John_GeoJSON_PDFs_20261106.zip'
    with zipfile.ZipFile(bundle,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths+geodata+[note]:z.write(p,p.name)
    print('BUNDLE',bundle,bundle.stat().st_size,flush=True)

if __name__=='__main__':main()
