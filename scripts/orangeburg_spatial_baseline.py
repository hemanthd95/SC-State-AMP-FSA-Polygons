"""Fetch official Census Orangeburg boundary and screen location hints (not fields)."""
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import json, zipfile
import requests, shapefile
from shapely.geometry import shape, Point

ROOT=Path(__file__).resolve().parents[1]
INVENTORY=ROOT/'analysis/orangeburg_source_inventory.json'
OUT=ROOT/'geojson/orangeburg_county_boundary.geojson'
SCREEN=ROOT/'analysis/orangeburg_coordinate_screening.json'
CENSUS='https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip'
response=requests.get(CENSUS,timeout=110)
response.raise_for_status()
z=zipfile.ZipFile(BytesIO(response.content))
shp=next(n for n in z.namelist() if n.endswith('.shp'))
dbf=next(n for n in z.namelist() if n.endswith('.dbf'))
sf=shapefile.Reader(shp=BytesIO(z.read(shp)),dbf=BytesIO(z.read(dbf)))
fields=[f[0] for f in sf.fields[1:]]
record=None
for item in sf.iterShapeRecords():
    attrs=dict(zip(fields,item.record))
    if attrs.get('GEOID')=='45075':
        record={'type':'Feature','properties':{
            'name':attrs.get('NAME'),'geoid':attrs.get('GEOID'),
            'source':'US Census 2024 Cartographic Boundary, 1:500,000',
            'source_url':CENSUS,
            'crs':'EPSG:4326 (NAD83 cartographic coordinates)'},
            'geometry':item.shape.__geo_interface__}
        break
if record is None:raise RuntimeError('Orangeburg county GEOID 45075 absent from source')
geom=shape(record['geometry'])
if not geom.is_valid or geom.is_empty:raise RuntimeError('Census county shape invalid')
OUT.parent.mkdir(parents=True,exist_ok=True)
OUT.write_text(json.dumps({'type':'FeatureCollection','features':[record]},indent=2)+'\n')
inv=json.loads(INVENTORY.read_text())
rows=[]
for fid,e in inv['farms'].items():
    if fid=='14043':continue  # Mary Koon withheld by producer request
    hints=[{'latitude':p['latitude'],'longitude':p['longitude'],
            'within_official_county':geom.covers(Point(p['longitude'],p['latitude'])),
            'distance_to_county_boundary_degrees':round(geom.distance(Point(p['longitude'],p['latitude'])),7)}
           for p in e.get('spreadsheet_coordinate_hints',[])]
    rows.append({'farm_id':fid,'producer':e['producer'],
                 'source_pdf_match':e['match_status'],
                 'roster_location_hints':hints,
                 'status':'COORDINATES_ONLY_NOT_FIELD_LOCATION'})
SCREEN.write_text(json.dumps({
    'county':'Orangeburg','county_geoid':'45075',
    'source_url':CENSUS,'generated_utc':datetime.now(timezone.utc).isoformat(),
    'excluded_farm_id':'14043',
    'warning':'Coordinate hints may be residential or incorrect. Outside-county hints do not prove farm is outside county. All field polygons require independent FSA identification and geometric QA.',
    'farm_hints':rows},indent=2)+'\n')
print('WROTE',OUT,'and',SCREEN,'farms',len(rows),flush=True)
