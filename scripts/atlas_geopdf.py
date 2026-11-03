"""Reproduce the admitted GeoPDF boundaries and validate against actual sources."""
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np
import pymupdf
from pyproj import Geod, Transformer
from shapely import union_all
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT = ROOT / 'outputs'
WORK = Path('/workspace/amp-atlas-work')
to_utm = Transformer.from_crs(4326, 32617, always_xy=True)
from_utm = Transformer.from_crs(32617, 4326, always_xy=True)
geod = Geod(ellps='WGS84')


def numbers(value):
    return list(map(float, re.findall(r'[-+]?(?:\d*\.\d+|\d+)', value)))


def georef(doc, page):
    vp = doc.xref_get_key(page.xref, 'VP')[1]
    bbox = numbers(re.search(r'/BBox\s*\[([^]]+)\]', vp).group(1))
    measure = int(re.search(r'/Measure\s+(\d+)\s+0\s+R', vp).group(1))
    lpts = np.array(numbers(doc.xref_get_key(measure, 'LPTS')[1])).reshape(-1, 2)
    gpts = np.array(numbers(doc.xref_get_key(measure, 'GPTS')[1])).reshape(-1, 2)
    east, north = to_utm.transform(gpts[:, 1], gpts[:, 0])
    reference = np.column_stack([east, north])
    design = np.column_stack([lpts, np.ones(len(lpts))])
    affine, *_ = np.linalg.lstsq(design, reference, rcond=None)
    residual = float(np.linalg.norm(design @ affine - reference, axis=1).max())

    def project(points):
        xy = np.array(points)
        local = np.column_stack([(xy[:, 0] - bbox[0]) / (bbox[2] - bbox[0]),
                                 (page.rect.height - xy[:, 1] - bbox[1]) / (bbox[3] - bbox[1]),
                                 np.ones(len(xy))])
        utm = local @ affine
        lon, lat = from_utm.transform(utm[:, 0], utm[:, 1])
        return np.column_stack([lon, lat]).tolist()
    return project, residual


def main():
    fields = json.loads((ROOT / 'geojson/master_fsa_fields_geopdf_verified.geojson').read_text())['features']
    qa = []
    reproduced = []
    for feature in fields:
        p = feature['properties']
        source = SOURCE / p['source_pdf']
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        doc = pymupdf.open(source)
        page = doc[p['page_number'] - 1]
        converter, residual = georef(doc, page)
        drawing = page.get_drawings()[p['source_draw_index']]
        vertices = []
        for item in drawing['items']:
            if item[0] != 'l':
                raise ValueError('Unsupported non-linear path; must review source')
            if not vertices:
                vertices.append(tuple(item[1]))
            vertices.append(tuple(item[2]))
        if vertices[0] != vertices[-1]:
            vertices.append(vertices[0])
        polygon = Polygon(converter(vertices))
        baseline = shape(feature['geometry'])
        displacement = transform(to_utm.transform, polygon).hausdorff_distance(transform(to_utm.transform, baseline))
        gdal_file = WORK / ('gdal_' + digest + '.json')
        if not gdal_file.exists():
            proc = subprocess.run(['gdalinfo', '-json', str(source)], capture_output=True, check=True)
            gdal_file.write_bytes(proc.stdout)
        gdal = json.loads(gdal_file.read_text())
        gt = gdal['geoTransform']
        gdal_to_utm = Transformer.from_crs(gdal['coordinateSystem']['wkt'], 32617, always_xy=True)
        discrepancy = []
        for pixel, lonlat in zip(vertices, polygon.exterior.coords):
            x = pixel[0] * gdal['size'][0] / page.rect.width
            y = pixel[1] * gdal['size'][1] / page.rect.height
            east = gt[0] + gt[1] * x + gt[2] * y
            north = gt[3] + gt[4] * x + gt[5] * y
            check_e, check_n = gdal_to_utm.transform(east, north)
            actual_e, actual_n = to_utm.transform(*lonlat)
            discrepancy.append(float(np.hypot(check_e - actual_e, check_n - actual_n)))
        gdal_difference = max(discrepancy)
        acres = abs(geod.geometry_area_perimeter(polygon)[0]) / 4046.8564224
        area_diff = 100 * (acres - float(p['fsa_reported_acres'])) / float(p['fsa_reported_acres'])
        acreage_pattern = re.escape(f"{float(p['fsa_reported_acres']):g}").replace(r'\.', r'\.\s*')
        label = re.compile(r'(?<![\d.])' + re.escape(str(p['field_id'])) + r'\s+' +
                           acreage_pattern + r'0*(?![\d.])')
        label_found = bool(label.search(page.get_text()))
        row = {'county': p['county'], 'farm_id': p['farm_id'], 'tract_id': p['tract_id'], 'field_id': p['field_id'],
               'source_pdf': p['source_pdf'], 'source_sha256_matches': digest == p['source_sha256'],
               'source_drawing_index': p['source_draw_index'], 'reproduced_geometry_valid': polygon.is_valid,
               'reported_fsa_acres': p['fsa_reported_acres'], 'reproduced_geodesic_acres': acres,
               'difference_percent': area_diff, 'affine_corner_fit_max_residual_m': residual,
               'baseline_boundary_hausdorff_m': displacement, 'printed_field_acre_pair_text_match': label_found,
               'independent_gdal_reference_max_difference_m': gdal_difference,
               'legacy_coordinate_issue': 'NORTH_SOUTH_REFERENCE_REVERSAL',
               'absolute_registration_accuracy': 'NOT_ESTABLISHED_BY_CORNER_FIT',
               'independent_basemap_alignment': 'PENDING_BASEMAP_ACCESS'}
        if not (row['source_sha256_matches'] and polygon.is_valid and abs(area_diff) < 1.5 and gdal_difference < 1):
            raise ValueError(json.dumps(row))
        qa.append(row)
        # Correct only the derived output; keep the original repository GeoJSON intact.
        copy = json.loads(json.dumps(feature))
        copy['geometry'] = mapping(polygon)
        copy['properties'].update({'source_sha256_rechecked': True,
                                   'source_vector_reproduced': True,
                                   'corner_fit_max_residual_m': residual,
                                   'gdal_reference_max_difference_m': gdal_difference,
                                   'geometry_status': 'SOURCE_VECTOR_AND_GDAL_REFERENCE_CHECKED_NOT_SURVEY',
                                   'coordinate_correction': 'NORTH_SOUTH_REFERENCE_REVERSAL_CORRECTED; original repository layer preserved',
                                   'polygon_calculated_acres': acres,
                                   'area_difference_percent': area_diff,
                                   'independent_imagery_alignment': 'PENDING'})
        reproduced.append(copy)
    (OUT / 'geojson/counties').mkdir(parents=True, exist_ok=True)
    (OUT / 'qa').mkdir(exist_ok=True)
    for filename in ['acreage_validation.csv', 'georeferencing_quality.csv']:
        with (OUT / 'qa' / filename).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(qa[0]))
            writer.writeheader()
            writer.writerows(qa)
    (OUT / 'geojson/SC_AMP_FSA_All_Farm_Fields.geojson').write_text(json.dumps({
        'type': 'FeatureCollection', 'features': reproduced,
    }, indent=2))
    groups = defaultdict(list)
    for f in reproduced:
        groups[(f['properties']['county'], f['properties']['farm_id'])].append(f)
    farms = []
    for (county, farm_id), members in sorted(groups.items()):
        union = union_all([shape(f['geometry']) for f in members])
        if union.geom_type == 'Polygon':
            union = MultiPolygon([union])
        assert union.is_valid
        farms.append({'type': 'Feature', 'properties': {
            'county': county, 'farm_id': farm_id,
            'tract_ids': sorted({f['properties']['tract_id'] for f in members}),
            'field_count': len(members),
            'sum_reported_fsa_acres': sum(float(f['properties']['fsa_reported_acres']) for f in members),
            'geometry_status': 'SOURCE_VECTOR_AND_AREA_CHECKED_NOT_SURVEY; independent imagery alignment pending',
            'coverage_scope': 'REGISTERED_GEOMETRIES_ONLY; unresolved farms listed in QA inventory',
        }, 'geometry': mapping(union)})
    (OUT / 'geojson/SC_AMP_FSA_All_Farms.geojson').write_text(json.dumps({
        'type': 'FeatureCollection', 'features': farms,
    }, indent=2))
    (OUT / 'geojson/Registered_Source_Farms.geojson').write_text(json.dumps({
        'type': 'FeatureCollection', 'features': farms,
    }, indent=2))
    all_counties = {f['county'] for f in json.loads((WORK / 'farm_inventory_private.json').read_text())}
    for county in sorted(all_counties):
        for suffix, features in [('Fields', reproduced), ('Farms', farms)]:
            (OUT / 'geojson/counties' / f'{county}_{suffix}.geojson').write_text(json.dumps({
                'type': 'FeatureCollection', 'features': [f for f in features if f['properties']['county'] == county],
            }, indent=2))
    print(json.dumps({'fields': len(reproduced), 'farm_groups': len(farms),
                      'max_reproduced_area_difference_percent': max(abs(r['difference_percent']) for r in qa),
                      'max_corner_fit_residual_m': max(r['affine_corner_fit_max_residual_m'] for r in qa),
                      'max_baseline_boundary_displacement_m': max(r['baseline_boundary_hausdorff_m'] for r in qa),
                      'max_independent_gdal_difference_m': max(r['independent_gdal_reference_max_difference_m'] for r in qa),
                      'printed_label_pairs_matched': sum(r['printed_field_acre_pair_text_match'] for r in qa)}, indent=2))


if __name__ == '__main__':
    main()
