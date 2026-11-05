"""Render the verified four-field Darlington atlas in both requested basemaps.

Two distinct source PDFs are image-registered to NAIP. Three Jackson fields
were listed in the Orangeburg AMP workbook, but their FSA page says Darlington.
The original roster county is retained inside the source GeoJSON.
"""
from collections import defaultdict
from pathlib import Path
import json

import fitz
from reportlab.pdfgen import canvas
from shapely.geometry import shape

from build_verified_atlases import (
    ROOT,W,H,draw_county,draw_detail,
)

OUT=ROOT/'darlington_working_atlas'
OUT.mkdir(exist_ok=True)
geojson=json.loads((ROOT/'geojson/darlington_registered_fields.geojson').read_text())
features=geojson['features']
assert len(features)==4
ids={(f['properties']['farm_id'],f['properties']['tract_id'],f['properties']['field_id']) for f in features}
assert ids=={('10262','10855','24'),('10262','10855','26'),('10262','10855','28'),('7370','442','1')}
farms=defaultdict(list)
for feature in features:
    p=feature['properties']
    assert p['county']=='Darlington' and shape(feature['geometry']).is_valid
    item={'type':'Feature','geometry':feature['geometry'],'properties':dict(p)}
    # Rendering code has a legacy Farm 8185-specific sidebar for a roster
    # reassignment. Do not print that unrelated provenance about Marva.
    # The published GeoJSON still preserves the original Orangeburg roster.
    item['properties']['original_amp_roster_county']=p['amp_roster_county']
    item['properties']['amp_roster_county']='Darlington'
    farms[p['farm_id']].append(item)

boundary=shape(next(f['geometry'] for f in json.loads((ROOT/'geojson/sc_counties_for_verified_atlases.geojson').read_text())['features']
                    if str(f['id']).zfill(5)=='45031'))

manifest=[]
for kind in ('Satellite','Topography'):
    output=OUT/f'Darlington_County_{kind}_4_Field_Atlas.pdf'
    c=canvas.Canvas(str(output),pagesize=(W,H),pageCompression=1)
    c.setTitle(f'Darlington AMP field atlas — {kind} — 2 farms / 4 FSA fields')
    c.setAuthor('South Carolina State University / AMP Geospatial Atlas')
    used=set()
    draw_county(c,'Darlington',farms,boundary,kind,used)
    for page,(fid,items) in enumerate(sorted(farms.items()),2):
        draw_detail(c,'Darlington',farms,fid,items,kind,page,used)
    c.save()
    with fitz.open(output) as report:
        assert len(report)==3,'Expect 1 overview and 2 farm close-up pages'
        assert all(report[i].get_images() for i in range(3)),'Map imagery missing from PDF'
    if output.stat().st_size<250000:raise RuntimeError('Atlas imagery suspiciously small')
    manifest.append({'basemap':kind,'pdf':output.name,'pages':3,'farms':2,
                     'fields':4,'bytes':output.stat().st_size,
                     'providers':sorted(used),'source_geometry':'FSA raster image registered to NAIP'})
    print('ATLAS',output.name,output.stat().st_size,flush=True)
(OUT/'darlington_atlas_manifest.json').write_text(json.dumps({
    'county':'Darlington','scope':'2 FSA source farms, 4 traced field polygons',
    'source_roster_warning':'Marva Jackson 3 fields originally appear in Orangeburg AMP spreadsheet; printed FSA source county is Darlington.',
    'garrett_census_boundary_warning':'Farm 7370 FSA printed Darlington; registered field center lies beyond supplied Census Darlington geometry. See GeoJSON provenance.',
    'geometric_accuracy_notice':'FSA image-derived approximate field outlines; not legal survey',
    'atlasses':manifest},indent=2)+'\n')
