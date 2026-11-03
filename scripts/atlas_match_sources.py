"""Associate source-map pages with farms, retaining uncertain matches explicitly."""
import csv
import hashlib
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
WORK = Path('/workspace/amp-atlas-work')


def normalized(text):
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


def main():
    farms = json.loads((WORK / 'farm_inventory_private.json').read_text())
    sources = json.loads((WORK / 'source_inspections.json').read_text())
    registered = json.loads((OUT / 'geojson/Registered_Source_Farms.geojson').read_text())['features']
    registered_keys = {(f['properties']['county'], str(f['properties']['farm_id'])) for f in registered if f['geometry'] is not None}
    boundary_features = json.loads((OUT / 'geojson/SC_County_Boundaries_Census_2022.geojson').read_text())['features']
    county_names = [f['properties']['NAME'] for f in boundary_features]
    audit = []
    page_ids = {}
    all_pages = []
    # Footer readings checked visually against rendered source pages after OCR.
    manual_ids = {
        ('Anthony Jackson_FSA_Map.pdf', 1): ['8185'],
        ('John_Lloyd_FSA_Map.pdf', 1): ['4198'],
        ('John_Lloyd_FSA_Map.pdf', 3): ['3756'],
        ('Jaylon carson_FSA Map.pdf', 1): ['14291'],
        ('Tywone Hillard_FSA_Map.pdf', 1): ['3873'],
        ('Tywone Hillard_FSA_Map.pdf', 3): ['960'],
        ('Montez Hillard_FSA _Map.pdf', 1): ['1033'],
        ('Brandon dingle FSAmap.pdf', 3): ['6750'],
        ('Brandon dingle FSAmap.pdf', 6): ['6750'],
    }
    for si, source in enumerate(sources):
        for page in source['pages']:
            if (source['source'], page['page']) in manual_ids:
                page['farm_ids_detected'] = manual_ids[(source['source'], page['page'])]
                page['identifier_method'] = 'VISUALLY_READ_SOURCE_MAP_FOOTER'
            tag = f'S{si + 1:03d}P{page["page"]:02d}'
            page_ids[(source['source'], page['page'])] = tag
            all_pages.append({'tag': tag, 'source': source['source'], 'sha256': source['sha256'], **page})
    # Administrative forms were identified in the complete source contact-sheet
    # review. They contain personal contact/tax information and are not map insets.
    excluded = {'S006P01', 'S006P02', 'S011P02', 'S036P02', 'S038P01', 'S038P02', 'S058P02'}
    excluded.update(f'S037P{i:02d}' for i in range(1, 6))
    for farm in farms:
        county, farm_id = farm['county'], farm['farm_id']
        names = {normalized(r['first'] + r['last']) for r in farm['records'] if r['first'] and r['last']}
        tracts = {x for r in farm['records'] for x in re.findall(r'\d+', r['tract_id'])}
        matches = []
        for source in sources:
            if source['source'].startswith('Producers by County/'):
                continue
            stem = re.sub(r'(fsa|map|farm|field|maps|estate|pdf|jpg|jpeg|copy|\d+)', '', Path(source['source']).stem, flags=re.I)
            name_score = max((SequenceMatcher(None, normalized(stem), name).ratio() for name in names), default=0)
            document_ids = {fid for pg in source['pages'] for fid in pg.get('farm_ids_detected', [])}
            for page in source['pages']:
                tag = page_ids[(source['source'], page['page'])]
                if 'error' in page or tag in excluded:
                    continue
                detected = set(page['farm_ids_detected'])
                exact = farm_id in detected
                county_match = bool(re.search(r'\b' + re.escape(county) + r'\s+County\b', page['text'], re.I))
                tract_match = bool(tracts.intersection(page['tract_ids_detected']))
                if exact and (county_match or tract_match or name_score >= .65):
                    method = 'FARM_ID_PLUS_COUNTY_TRACT_OR_NAME'
                    score = 100 + 10 * county_match + 10 * tract_match + name_score
                elif exact and not detected.difference({farm_id}):
                    method = 'FARM_ID_ONLY_COUNTY_IDENTITY_REVIEW'
                    score = 70 + name_score
                elif name_score >= .73 and not detected and not document_ids:
                    method = 'FILENAME_CANDIDATE_IDENTITY_REVIEW_PENDING'
                    score = 40 + name_score
                else:
                    continue
                source_counties = [c for c in county_names if re.search(
                    r'\b' + re.escape(c) + r'\s+County\b(?!\s*FSA\s+Office)', page['text'], re.I)]
                county_warning = ''
                if len(source_counties) == 1 and source_counties[0] != county:
                    county_warning = f'Source map prints {source_counties[0]} County; inventory lists {county}. County assignment requires reconciliation.'
                    method = 'SOURCE_COUNTY_CONFLICT_REVIEW_REQUIRED'
                matches.append({'source': source['source'], 'page': page['page'],
                                'tag': page_ids[(source['source'], page['page'])],
                                'sha256': source['sha256'], 'image_file': page['image_file'],
                                'match_method': method, 'score': score,
                                'identity_warning': county_warning,
                                'page_farm_ids': page['farm_ids_detected'],
                                'map_registration': 'GEOPDF' if source['geospatial_objects'] else 'UNREGISTERED'})
        # Same binary source may have multiple filenames; retain one displayed page.
        if any(m['match_method'] == 'FARM_ID_PLUS_COUNTY_TRACT_OR_NAME' for m in matches):
            matches = [m for m in matches if m['match_method'] == 'FARM_ID_PLUS_COUNTY_TRACT_OR_NAME']
        seen = set()
        farm['source_matches'] = []
        for match in sorted(matches, key=lambda m: (-m['score'], m['source'], m['page'])):
            key = hashlib.sha256(Path(match['image_file']).read_bytes()).hexdigest()
            if key not in seen:
                seen.add(key)
                farm['source_matches'].append(match)
        conflict_sources = {
            ('Allendale', '10333'): ('Samuel Lance JR.pdf', 1, 'Source prints Farm 3740 / Tract 10333; enrollment Farm 10333 / Tract 2161. Identity and county require reconciliation.'),
            ('Clarendon', '1694'): ('Timothy J Hilliard_FSA_Map.pdf', 1, 'Source prints Farm 1634; enrollment Farm 1694. Tract identifiers also differ; do not assume a typo correction.'),
        }
        if not farm['source_matches'] and (county, farm_id) in conflict_sources:
            filename, page_number, warning = conflict_sources[(county, farm_id)]
            source = next(s for s in sources if s['source'] == filename)
            pg = next(p for p in source['pages'] if p['page'] == page_number)
            farm['source_matches'].append({'source': filename, 'page': page_number,
                'tag': page_ids[(filename, page_number)], 'sha256': source['sha256'],
                'image_file': pg['image_file'], 'match_method': 'FILENAME_IDENTITY_CONFLICT_REVIEW_REQUIRED',
                'score': 0, 'page_farm_ids': pg['farm_ids_detected'], 'map_registration': 'UNREGISTERED',
                'identity_warning': warning})
        farm['registered_field_geometry'] = (county, farm_id) in registered_keys
        farm['extraction_status'] = ('GEOREFERENCED_VECTOR_SOURCE_AND_GDAL_CHECKED' if farm['registered_field_geometry'] else
                                     ('SOURCE_IDENTITY_REVIEW_REQUIRED' if farm['source_matches'] and all('REVIEW' in m['match_method'] for m in farm['source_matches']) else
                                      ('SOURCE_BOUNDARY_REGISTRATION_PENDING' if farm['source_matches'] else 'NO_CONFIRMED_SOURCE_MAP_MATCH')))
        audit.append({'county': county, 'farm_id': farm_id, 'extraction_status': farm['extraction_status'],
                      'matched_or_candidate_source_pages': len(farm['source_matches']),
                      'identity_review_required': any('REVIEW' in m['match_method'] for m in farm['source_matches']),
                      'source_pages': '; '.join(f"{m['source']} [p{m['page']}; {m['match_method']}; {m.get('identity_warning', '')}]" for m in farm['source_matches']),
                      'registration_quality': 'INTERNAL_GEOPDF_REFERENCE_ONLY; not survey accuracy' if farm['registered_field_geometry'] else 'NOT_ESTABLISHED'})
    (WORK / 'farm_inventory_matched_private.json').write_text(json.dumps(farms, indent=2))
    (WORK / 'all_source_pages_private.json').write_text(json.dumps(all_pages, indent=2))
    with (OUT / 'qa/polygon_extraction_status.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(audit[0]))
        writer.writeheader()
        writer.writerows(audit)
    with (OUT / 'qa/source_manual_identifier_readings.csv').open('w', newline='') as stream:
        writer = csv.writer(stream); writer.writerow(['source_file', 'page', 'visually_read_farm_id', 'method'])
        for (filename, page), read_ids in manual_ids.items():
            writer.writerow([filename, page, ';'.join(read_ids), 'VISUAL_SOURCE_FOOTER_REVIEW'])
    print('Farm extraction status:', dict(Counter(f['extraction_status'] for f in farms)))
    print('Matched or candidate page associations:', sum(len(f['source_matches']) for f in farms))


if __name__ == '__main__':
    main()
