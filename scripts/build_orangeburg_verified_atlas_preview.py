"""Render a visibly incomplete but fully georegistered Orangeburg atlas preview.

Unlike an unregistered PDF source collage, every featured field is a QA-passed
GeoJSON polygon drawn over fresh satellite or topographic map imagery.
Never call a verified-subset preview the final county atlas. The filename and\nfooter reflect the current exact number of QA-passed fields.
"""
from pathlib import Path
from collections import defaultdict
import json,fitz
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from shapely.geometry import shape
from build_verified_atlases import (ROOT,W,H,NAVY,GRAY,font,draw_county,draw_detail)
OUT=ROOT/'orangeburg_working_atlas'
OUT.mkdir(exist_ok=True)
features=json.loads((ROOT/'geojson/orangeburg_registered_fields.geojson').read_text())['features']
assert 1<=len(features)<32,'Temporary preview expects verified subset of 32 requested fields'
count=len(features);remaining=32-count
farms=defaultdict(list)
for record in features:
    p=record['properties']
    assert p['county']=='Orangeburg' and p['status']=='IMAGE_REGISTERED_AND_VISUALLY_QA_PASSED'
    if not shape(record['geometry']).is_valid:raise ValueError('Invalid verified polygon')
    f={'type':'Feature','geometry':record['geometry'],'properties':dict(p)}
    f['properties'].update({
      'county_workbook_selected':True,'amp_roster_county':'Orangeburg',
      'fsa_reported_acres':p['fsa_printed_acres'],'method':'raster image registration',
      'image_registration_inliers':p['registration_inliers']})
    farms[str(p['farm_id'])].append(f)
boundary=shape(json.loads((ROOT/'geojson/orangeburg_county_boundary.geojson').read_text())['features'][0]['geometry'])
for f in features:
    if not boundary.covers(shape(f['geometry']).representative_point()):
        raise ValueError('Field outside official county: '+f['properties']['farm_id'])
manifest=[]
for kind in ('Satellite','Topography'):
    path=OUT/f'Orangeburg_County_{kind}_DRAFT_{count}of32.pdf'
    c=canvas.Canvas(str(path),pagesize=(W,H),pageCompression=1)
    c.setTitle(f'DRAFT Orangeburg AMP / FSA county {kind} atlas — {count} of 32 fields')
    c.setAuthor('South Carolina State University AMP geospatial atlas development')
    old_show=c.showPage
    def show_page_with_provisional_label():
        c.saveState()
        c.setFillColor(colors.HexColor('#A03D34'))
        c.setFont('Helvetica-Bold',11)
        c.drawCentredString(W/2,84,
          f'INCOMPLETE QA PREVIEW  /  {count} OF 32 VERIFIED FIELDS  /  {remaining} FIELDS STILL UNDER REVIEW')
        c.restoreState()
        old_show()
    c.showPage=show_page_with_provisional_label
    used=set()
    draw_county(c,'Orangeburg',farms,boundary,kind,used)
    for number,(fid,fields) in enumerate(sorted(farms.items()),2):
        draw_detail(c,'Orangeburg',farms,fid,fields,kind,number,used)
    c.save()
    with fitz.open(path) as pdf:
        if len(pdf)!=len(farms)+1:raise RuntimeError('Missing atlas PDF pages')
    if path.stat().st_size<120000:raise RuntimeError('PDF suspiciously small')
    manifest.append({'kind':kind,'filename':path.name,'farms':len(farms),
                     'verified_fields':count,'unverified_fields':remaining,
                     'pages':len(farms)+1,'bytes':path.stat().st_size,
                     'imagery_services':sorted(used),'is_final':False})
    print('DRAFT ATLAS',path.name,'pages',len(farms)+1,flush=True)
(OUT/'preview_manifest.json').write_text(json.dumps({
 'status':'INCOMPLETE_VERIFIED_ONLY_QA_PREVIEW',
 'warning':f'{remaining} of 32 Orangeburg field geometries still unverified. This is not the completed Orangeburg atlas.',
 'mary_koon_farm14043':'EXCLUDED_AS_USER_REQUESTED',
 'atlases':manifest},indent=2)+'\n')
