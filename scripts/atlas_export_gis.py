"""Export reconciled layers; unresolved farms get null boundaries, never buffers."""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import shapefile
from pyproj import CRS, Transformer
from shapely.geometry import Point, mapping, shape
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
WORK = Path('/workspace/amp-atlas-work')


def collection(path, features):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({'type': 'FeatureCollection', 'features': features}, indent=2))


def shape_export(path, features, kind):
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = shapefile.Writer(str(path), shapeType=kind, encoding='utf-8')
    writer.field('county', 'C', 24)
    writer.field('farm_id', 'C', 20)
    writer.field('tract_id', 'C', 80)
    writer.field('field_id', 'C', 40)
    writer.field('fsa_acres', 'N', 18, 4)
    writer.field('status', 'C', 160)
    for feature in features:
        p = feature['properties']
        if feature['geometry'] is None:
            writer.null()
        elif kind == shapefile.POINT:
            writer.point(*feature['geometry']['coordinates'])
        else:
            geom = shape(feature['geometry'])
            polygons = [geom] if geom.geom_type == 'Polygon' else list(geom.geoms)
            parts = []
            for polygon in polygons:
                polygon = orient(polygon, sign=-1)
                parts.append(list(polygon.exterior.coords))
                parts.extend(list(ring.coords) for ring in polygon.interiors)
            writer.poly(parts)
        writer.record(str(p.get('county') or ''), str(p.get('farm_id') or ''),
                      str(p.get('tract_id', p.get('tract_ids', ''))), str(p.get('field_id', '')),
                      p.get('fsa_reported_acres'), str(p.get('geometry_status', p.get('location_status', ''))))
    writer.close()
    path.with_suffix('.prj').write_text(CRS.from_epsg(4326).to_wkt(version='WKT1_ESRI'))
    path.with_suffix('.cpg').write_text('UTF-8')
    assert len(shapefile.Reader(str(path))) == len(features)


def main():
    farms = json.loads((WORK / 'farm_inventory_matched_private.json').read_text())
    missing = json.loads((WORK / 'enrollment_records_missing_farm_id_private.json').read_text())
    sources = json.loads((OUT / 'geojson/Registered_Source_Farms.geojson').read_text())['features']
    fields = json.loads((OUT / 'geojson/SC_AMP_FSA_All_Farm_Fields.geojson').read_text())['features']
    known = {(f['county'], f['farm_id']) for f in farms}
    source_lookup = {(f['properties']['county'], str(f['properties']['farm_id'])): f for f in sources}
    collection(OUT / 'geojson/Registered_Source_Farms.geojson', sources)
    collection(OUT / 'geojson/Source_Only_Registered_Farms.geojson', [f for f in sources if (f['properties']['county'], str(f['properties']['farm_id'])) not in known])
    for f in fields:
        p = f['properties']
        p['enrollment_farm_match'] = (p['county'], str(p['farm_id'])) in known
        p['field_enrollment_status'] = 'SOURCE_FIELD; program enrollment must be checked against field crosswalk'
    collection(OUT / 'geojson/SC_AMP_FSA_All_Farm_Fields.geojson', fields)
    farm_features, points = [], []
    for farm in farms:
        key = (farm['county'], farm['farm_id'])
        source = source_lookup.get(key)
        props = {'county': farm['county'], 'farm_id': farm['farm_id'],
                 'record_count': farm['record_count'], 'enrollment_scopes': farm['scopes'],
                 'tract_ids': sorted({r['tract_id'] for r in farm['records'] if r['tract_id']}),
                 'extraction_status': farm['extraction_status'],
                 'reported_longitude': farm['reported_longitude'], 'reported_latitude': farm['reported_latitude'],
                 'reported_coordinate_in_county': farm['reported_coordinate_in_county'],
                 'coordinate_conflict': farm['coordinate_conflict'],
                 'field_count': source['properties']['field_count'] if source else 0,
                 'geometry_status': 'SOURCE_VECTOR_AND_GDAL_REFERENCE_CHECKED_NOT_SURVEY' if source else 'BOUNDARY_UNRESOLVED_NULL_GEOMETRY'}
        farm_features.append({'type': 'Feature', 'properties': props, 'geometry': source['geometry'] if source else None})
        point = shape(source['geometry']).representative_point() if source else None
        location_status = 'REGISTERED_SOURCE_POLYGON_REPRESENTATIVE_POINT' if point else farm['location_status']
        if point is None and farm['location_status'] == 'APPROXIMATE_REPORTED_COORDINATE':
            point = Point(farm['reported_longitude'], farm['reported_latitude'])
        points.append({'type': 'Feature', 'properties': {**props, 'location_status': location_status},
                       'geometry': mapping(point) if point else None})
    collection(OUT / 'geojson/SC_AMP_FSA_All_Farms.geojson', farm_features)
    collection(OUT / 'geojson/SC_AMP_FSA_Farm_Locations.geojson', points)
    unresolved = [{'type': 'Feature', 'geometry': None, 'properties': {
        'county': r['county'] or None, 'farm_id': None, 'amp_producer_id': r['amp_producer_id'],
        'source': r['source'], 'sheet': r['sheet'], 'row': r['row'],
        'geometry_status': 'MISSING_FARM_ID; source association and county/location review pending',
    }} for r in missing]
    collection(OUT / 'geojson/Unresolved_Enrollment_Records.geojson', unresolved)
    shape_export(OUT / 'shapefiles/Unresolved_Enrollment_Records', unresolved, shapefile.POINT)
    for county in sorted({f['county'] for f in farms} | {r['county'] for r in missing if r['county']}):
        for label, features, kind in [('Fields', fields, shapefile.POLYGON), ('Farms', farm_features, shapefile.POLYGON), ('Locations', points, shapefile.POINT)]:
            selected = [f for f in features if f['properties']['county'] == county]
            collection(OUT / 'geojson/counties' / f'{county}_{label}.geojson', selected)
            shape_export(OUT / 'shapefiles/counties' / f'{county}_{label}', selected, kind)
    geometry_keys = {(str(f['properties']['county']), str(f['properties']['farm_id']),
                      str(f['properties']['tract_id']), str(f['properties']['field_id'])) for f in fields}
    crosswalk = []
    for farm in farms:
        for r in farm['records']:
            tracts = re.findall(r'\d+', r['tract_id'])
            field_ids = re.findall(r'\d+', r['field_id'])
            unambiguous = len(r['farm_ids']) == 1 and len(tracts) == 1 and bool(field_ids)
            count = sum((farm['county'], farm['farm_id'], tracts[0], field) in geometry_keys for field in field_ids) if unambiguous else 0
            crosswalk.append({'county': farm['county'], 'farm_id': farm['farm_id'], 'source': r['source'],
                              'sheet': r['sheet'], 'row': r['row'], 'scope': r['scope'],
                              'tract_ids_as_supplied': r['tract_id'], 'field_ids_as_supplied': r['field_id'],
                              'unambiguous_field_id_count': len(field_ids) if unambiguous else '',
                              'matched_registered_field_ids': count,
                              'status': ('ASSOCIATION_AMBIGUOUS_REVIEW' if not unambiguous else
                                         ('ALL_LISTED_FIELDS_MATCH_REGISTERED_GEOMETRY' if count == len(field_ids) else 'SOME_OR_ALL_LISTED_FIELDS_HAVE_NO_REGISTERED_GEOMETRY'))})
    with (OUT / 'qa/enrolled_field_geometry_crosswalk.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(crosswalk[0])); writer.writeheader(); writer.writerows(crosswalk)
    summary = {'listed_farm_features': len(farm_features), 'registered_participant_farm_boundaries': sum(f['geometry'] is not None for f in farm_features),
               'null_farm_boundaries': sum(f['geometry'] is None for f in farm_features),
               'registered_source_fields': len(fields), 'source_only_unreconciled_farm_boundaries': sum(k not in known for k in source_lookup),
               'usable_location_points': sum(f['geometry'] is not None for f in points),
               'warning': 'All Farms includes null boundaries; Source Fields includes source-map fields not necessarily enrolled. Use crosswalk.'}
    (OUT / 'qa/gis_export_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
