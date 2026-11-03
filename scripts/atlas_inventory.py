"""Reconcile county and enrollment workbooks without exposing contact details."""
import csv
import hashlib
import json
import re
import warnings
from difflib import SequenceMatcher
from collections import Counter, defaultdict
from pathlib import Path

from openpyxl import load_workbook
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
WORK = Path('/workspace/amp-atlas-work')
OUT = ROOT / 'outputs'
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')


def county_name(value):
    text = str(value or '').strip().replace('County', '').strip().title()
    return {'Berkley': 'Berkeley', 'Colletton': 'Colleton', 'Malboro': 'Marlboro',
            'Marrion': 'Marion', 'Allandale': 'Allendale'}.get(text, text)


def text_id(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def ids(value):
    return list(dict.fromkeys(re.findall(r'\d+', text_id(value))))


def coordinate(x, y):
    def number(v):
        try:
            return float(str(v).strip().replace('°', '').replace(',', ''))
        except (TypeError, ValueError):
            return None
    x, y = number(x), number(y)
    if x is None or y is None:
        return None, None, 'MISSING_OR_UNPARSEABLE'
    if 32 < x < 36 and -84 < y < -78:
        return y, x, 'X_IS_LATITUDE_Y_IS_LONGITUDE'
    if -84 < x < -78 and 32 < y < 36:
        return x, y, 'X_IS_LONGITUDE_Y_IS_LATITUDE'
    return None, None, 'OUTSIDE_PLAUSIBLE_SC_RANGE'


def csv_write(filename, rows, columns=None):
    path = OUT / 'qa' / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns or list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    folder = SOURCE / 'Producers by County'
    records = []
    workbook_summary = []
    for path in sorted(folder.glob('*County*.xlsx')):
        workbook = load_workbook(path, read_only=True, data_only=True)
        county = county_name(path.stem.split('County')[0])
        count = 0
        for row_number, row in enumerate(workbook.active.iter_rows(max_col=26, values_only=True), 1):
            if row_number == 1 or not text_id(row[2]):
                continue
            lon, lat, status = coordinate(row[6], row[7])
            records.append({'source': str(path.relative_to(SOURCE)), 'sheet': workbook.active.title,
                            'row': row_number, 'scope': 'county_workbook', 'county': county,
                            'first': text_id(row[0]), 'last': text_id(row[1]),
                            'farm_ids': ids(row[2]), 'raw_farm_id': text_id(row[2]),
                            'tract_id': text_id(row[3]), 'field_id': text_id(row[4]),
                            'longitude': lon, 'latitude': lat, 'coordinate_status': status,
                            'reported_acres': None, 'amp_producer_id': '',
                            'county_cell': text_id(row[8])})
            count += 1
        workbook_summary.append({'county': county, 'county_workbook_rows': count})
        workbook.close()

    # These master workbooks contain the same enrollment tables. Read both and
    # deduplicate records while retaining both source references.
    seen = {}
    enrollment_no_farm = []
    for path in sorted(folder.glob('All*.xlsx')):
        workbook = load_workbook(path, read_only=True, data_only=True)
        for sheet in workbook:
            if 'Enrollment' not in sheet.title:
                continue
            year2 = '2' in sheet.title
            for row_number, row in enumerate(sheet.iter_rows(max_col=35, values_only=True), 1):
                if row_number <= (2 if year2 else 1):
                    continue
                first, last = (row[2], row[3]) if year2 else (row[0], row[1])
                if not text_id(first) and not text_id(last):
                    continue
                raw_farm, tract, field = (row[13], row[14], row[15]) if year2 else (row[11], row[12], row[13])
                county = county_name(row[10] if year2 else row[9])
                signature = (sheet.title, text_id(first).lower(), text_id(last).lower(),
                             text_id(raw_farm), text_id(tract), text_id(field), county)
                if signature in seen:
                    seen[signature]['additional_sources'].append(str(path.relative_to(SOURCE)))
                    continue
                lon, lat, status = coordinate(None, None) if year2 else coordinate(row[5], row[6])
                record = {'source': str(path.relative_to(SOURCE)), 'additional_sources': [],
                          'sheet': sheet.title, 'row': row_number,
                          'scope': 'enrollment_year_2' if year2 else 'enrollment_year_1',
                          'county': county, 'first': text_id(first), 'last': text_id(last),
                          'farm_ids': ids(raw_farm), 'raw_farm_id': text_id(raw_farm),
                          'tract_id': text_id(tract), 'field_id': text_id(field),
                          'longitude': lon, 'latitude': lat, 'coordinate_status': status,
                          'reported_acres': row[16] if year2 else row[14],
                          'amp_producer_id': text_id(row[0]) if year2 else '', 'county_cell': county}
                seen[signature] = record
                if not record['farm_ids']:
                    enrollment_no_farm.append(record)
                else:
                    records.append(record)
        workbook.close()

    boundary_file = WORK / 'census_counties_2022.json'
    boundaries = {}
    if boundary_file.exists() and boundary_file.stat().st_size:
        data = json.loads(boundary_file.read_text())
        sc = [f for f in data['features'] if str(f['properties'].get('STATEFP')) == '45']
        boundaries = {f['properties']['NAME']: shape(f['geometry']) for f in sc}
        (OUT / 'geojson').mkdir(parents=True, exist_ok=True)
        (OUT / 'geojson/SC_County_Boundaries_Census_2022.geojson').write_text(json.dumps({
            'type': 'FeatureCollection', 'features': sc,
        }))

    # Correct county assignments only when a known GeoPDF Farm/Tract pair,
    # unchanged source hash and printed identifiers support the county, and a
    # source-map filename independently agrees with the enrollment name.
    geo_pairs = defaultdict(set)
    source_inspections = json.loads((WORK / 'source_inspections.json').read_text()) if (WORK / 'source_inspections.json').exists() else []
    # Visually read from the photographed FSA map footer (Farm 8185 / Tract
    # 2352). OCR missed this footer; the source image itself was inspected.
    for source in source_inspections:
        if source['source'] == 'Anthony Jackson_FSA_Map.pdf':
            source['pages'][0]['farm_ids_detected'] = ['8185']
            source['pages'][0]['tract_ids_detected'] = ['2352']
    by_source = {s['source']: s for s in source_inspections}
    admitted = json.loads((ROOT / 'geojson/master_fsa_fields_geopdf_verified.geojson').read_text())['features']
    for feature in admitted:
        p = feature['properties']; source = by_source.get(p['source_pdf'])
        if not source or source['sha256'] != p['source_sha256']:
            continue
        if any(str(p['farm_id']) in pg['farm_ids_detected'] and str(p['tract_id']) in pg['tract_ids_detected']
               and re.search(r'\b'+re.escape(p['county'])+r'\s+County\b',pg['text'],re.I) for pg in source['pages']):
            geo_pairs[(str(p['farm_id']), str(p['tract_id']))].add(p['county'])
    corrections = []
    for record in records:
        record['original_county'] = record['county']
        tract_ids = ids(record['tract_id'])
        if len(record['farm_ids']) != 1 or len(tract_ids) != 1:
            continue
        pair = (record['farm_ids'][0], tract_ids[0])
        supported = geo_pairs.get(pair, set())
        if len(supported) != 1 or record['county'] in supported:
            continue
        corrected = next(iter(supported))
        name = re.sub(r'[^a-z0-9]', '', (record['first']+record['last']).lower())
        supporting_sources = []
        for source in source_inspections:
            stem = re.sub(r'(fsa|maps|map|farm|copy|\d+)', '', Path(source['source']).stem, flags=re.I)
            stem = re.sub(r'[^a-z0-9]', '', stem.lower())
            if SequenceMatcher(None, name, stem).ratio() < .73:
                continue
            if any(pair[0] in pg['farm_ids_detected'] and pair[1] in pg['tract_ids_detected'] for pg in source['pages']):
                supporting_sources.append(source['source'])
        if supporting_sources:
            corrections.append({'source': record['source'], 'sheet': record['sheet'], 'row': record['row'],
                                'farm_id': pair[0], 'tract_id': pair[1], 'original_county': record['county'],
                                'corrected_county': corrected,
                                'evidence': 'HASH_CHECKED_GEOPDF_PRINTED_FARM_TRACT_COUNTY_PLUS_FILENAME_NAME_MATCH',
                                'supporting_sources': '; '.join(supporting_sources)})
            record['county'] = corrected
    csv_write('county_assignment_corrections.csv', corrections,
              ['source','sheet','row','farm_id','tract_id','original_county','corrected_county','evidence','supporting_sources'])
    grouped = defaultdict(list)
    for record in records:
        for farm_id in record['farm_ids']:
            grouped[(record['county'], farm_id)].append(record)
    farms = []
    for (county, farm_id), members in sorted(grouped.items()):
        scopes = sorted({r['scope'] for r in members})
        points = [r for r in members if r['longitude'] is not None]
        points.sort(key=lambda r: (r['scope'] != 'county_workbook', r['source'], r['row']))
        loc = points[0] if points else None
        conflict = len({(round(r['longitude'], 5), round(r['latitude'], 5)) for r in points}) > 1
        in_county = (boundaries[county].covers(Point(loc['longitude'], loc['latitude']))
                     if loc and county in boundaries else None)
        farms.append({'county': county, 'farm_id': farm_id, 'record_count': len(members),
                      'scopes': scopes, 'records': members,
                      'amp_producer_ids': sorted({r['amp_producer_id'] for r in members if r['amp_producer_id']}),
                      'reported_longitude': loc['longitude'] if loc else None,
                      'reported_latitude': loc['latitude'] if loc else None,
                      'coordinate_conflict': conflict, 'reported_coordinate_in_county': in_county,
                      'coordinate_source': f"{loc['source']}::{loc['sheet']}::{loc['row']}" if loc else '',
                      'multi_farm_record_association_pending': any(len(r['farm_ids']) > 1 for r in members),
                      'location_status': 'APPROXIMATE_REPORTED_COORDINATE' if loc and in_county is not False else
                      ('REPORTED_COORDINATE_OUTSIDE_COUNTY_REVIEW' if loc else 'NO_USABLE_COORDINATE')})

    WORK.mkdir(exist_ok=True)
    (WORK / 'producer_records_private.json').write_text(json.dumps(records, default=str, indent=2))
    (WORK / 'enrollment_records_missing_farm_id_private.json').write_text(json.dumps(enrollment_no_farm, default=str, indent=2))
    (WORK / 'farm_inventory_private.json').write_text(json.dumps(farms, default=str, indent=2))
    sanitized = [{k: (json.dumps(v) if isinstance(v, list) else v) for k, v in f.items() if k != 'records'} for f in farms]
    csv_write('farm_inventory.csv', sanitized)
    county_rows = []
    for county in sorted({f['county'] for f in farms}):
        subset = [f for f in farms if f['county'] == county]
        county_rows.append({'county': county, 'distinct_county_scoped_farm_ids': len(subset),
                            'farms_in_county_workbooks': sum('county_workbook' in f['scopes'] for f in subset),
                            'farms_in_year_2_enrollment': sum('enrollment_year_2' in f['scopes'] for f in subset),
                            'farms_only_in_year_1_enrollment': sum(f['scopes'] == ['enrollment_year_1'] for f in subset),
                            'reported_points_outside_county': sum(f['reported_coordinate_in_county'] is False for f in subset),
                            'farms_without_coordinates': sum(f['reported_longitude'] is None for f in subset),
                            'satellite_pdf_status': 'PENDING_BASEMAP_ACCESS_AND_SOURCE_QA',
                            'topographic_pdf_status': 'PENDING_BASEMAP_ACCESS_AND_SOURCE_QA'})
    csv_write('county_coverage.csv', county_rows)
    csv_write('producer_record_reconciliation.csv', [{
        'source': r['source'], 'sheet': r['sheet'], 'row': r['row'], 'scope': r['scope'],
        'county': r['county'], 'raw_farm_id': r['raw_farm_id'], 'tract_id': r['tract_id'],
        'original_county': r.get('original_county',r['county']),
        'field_id': r['field_id'], 'coordinate_status': r['coordinate_status'],
        'county_formula_error': r['county_cell'] == '#VALUE!',
        'association_status': 'MULTI_FARM_IDENTIFIERS_ASSOCIATION_PENDING' if len(r['farm_ids']) > 1 else 'SINGLE_FARM_ID',
    } for r in records])
    csv_write('enrollment_records_missing_farm_id.csv', [{
        'source': r['source'], 'sheet': r['sheet'], 'row': r['row'],
        'county': r['county'], 'amp_producer_id': r['amp_producer_id'],
        'status': 'MISSING_FARM_ID_REQUIRES_RECONCILIATION',
    } for r in enrollment_no_farm], ['source', 'sheet', 'row', 'county', 'amp_producer_id', 'status'])
    summary = {'county_workbook_count': len(workbook_summary),
               'county_workbook_rows': sum(r['county_workbook_rows'] for r in workbook_summary),
               'county_workbook_distinct_county_scoped_farms': sum('county_workbook' in f['scopes'] for f in farms),
               'all_supplied_enrollment_scopes_counties': len(county_rows),
               'all_supplied_enrollment_scopes_county_farm_ids': len(farms),
               'deduplicated_master_records_missing_farm_id': len(enrollment_no_farm),
               'county_boundaries_available': len(boundaries),
               'source_supported_county_corrections': len(corrections),
               'coordinate_status_counts': dict(Counter(r['coordinate_status'] for r in records)),
               'scope_note': 'Union of supplied county workbooks and Year 1/Year 2 enrollment. Historical enrollment is distinguished; current participation is not assumed.'}
    (OUT / 'qa/reconciliation_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
