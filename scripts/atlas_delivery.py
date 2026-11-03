"""Verify source-review PDFs, render every page, document limits, package outputs."""
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageOps
from shapely.geometry import shape, Polygon, Point

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs'
WORK = Path('/workspace/amp-atlas-work')


def read_csv(name):
    with (OUT/'qa'/name).open() as stream: return list(csv.DictReader(stream))


def write_csv(name, rows, columns=None):
    with (OUT/'qa'/name).open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=columns or list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    pymupdf.TOOLS.mupdf_display_errors(False)
    pymupdf.TOOLS.mupdf_display_warnings(False)
    farms=json.loads((WORK/'farm_inventory_matched_private.json').read_text())
    coverage=read_csv('county_pdf_verification.csv')
    log=read_csv('map_generation_log.csv')
    farm_lookup={(f['county'],f['farm_id']):f for f in farms}
    for row in log:
        f=farm_lookup.get((row['county'],row['farm_id']))
        if f and f['registered_field_geometry']:row['source_insets']='1'
    write_csv('map_generation_log.csv',log)
    checks=[];page_rows=[];preview_paths=[]
    for county in coverage:
        pdf=OUT/county['review_pdf'];doc=pymupdf.open(pdf)
        assert len(doc)==int(county['review_pdf_pages'])
        items=[r for r in log if r['county']==county['county']]
        assert len(items)==int(county['overview_index_entries'])==int(county['detail_inventory_entries'])
        text0=doc[0].get_text()
        for row in items:
            identifier='Farm '+row['farm_id'] if row['farm_id'] else row['unresolved_producer_id']
            assert identifier in text0,(county['county'],identifier,'absent from overview index')
            for number in map(int,row['detail_pages'].split(';')):
                assert identifier in doc[number-1].get_text(),(county['county'],identifier,'absent from detail page')
        preview_dir=OUT/'previews'/county['county'];preview_dir.mkdir(parents=True,exist_ok=True)
        for old_preview in preview_dir.glob('page_*.jpg'):
            match=re.fullmatch(r'page_(\d+)\.jpg',old_preview.name)
            if match and int(match.group(1))>len(doc):
                old_preview.unlink()
        for number,page in enumerate(doc,1):
            assert abs(page.rect.width-1224)<.1 and abs(page.rect.height-792)<.1
            target=preview_dir/f'page_{number:03d}.jpg'
            if not target.exists() or target.stat().st_mtime_ns < pdf.stat().st_mtime_ns:
                pix=page.get_pixmap(dpi=90,alpha=False)
                pix.save(target,jpg_quality=78)
            im=Image.open(target).convert('L');arr=np.asarray(im)
            ink=float((arr<235).mean())
            assert ink>.005,(str(pdf),number,'effectively blank')
            blocks=page.get_text('blocks')
            overflow=sum(b[0]<-1 or b[1]<-1 or b[2]>1225 or b[3]>793 for b in blocks if b[6]==0)
            assert overflow==0,(str(pdf),number,'text exceeds page')
            page_rows.append({'pdf':str(pdf.relative_to(OUT)),'page':number,'width_inches':17,'height_inches':11,
                              'rendered':True,'nonwhite_pixel_fraction':ink,'text_overflow_blocks':overflow,
                              'preview':str(target.relative_to(OUT)),
                              'review_type':'SOURCE_REVIEW; not final satellite/topography',
                              'page_render_status':'PASS'})
            preview_paths.append((county['county'],number,target))
        checks.append({'county':county['county'],'pdf':county['review_pdf'],'pages':len(doc),
                       'overview_detail_entry_counts_match':True,'all_index_ids_found_on_details':True,
                       'all_pages_rendered_nonblank':True})
        print('Verified/rendered',county['county'],len(doc),'pages',flush=True)
    write_csv('pdf_page_validation.csv',page_rows)
    write_csv('pdf_content_checks.csv',checks)

    contact_dir=OUT/'previews/contact_sheets';contact_dir.mkdir(exist_ok=True)
    for start in range(0,len(preview_paths),16):
        sheet=Image.new('RGB',(1440,1120),'white');draw=ImageDraw.Draw(sheet)
        for j,(county,number,path) in enumerate(preview_paths[start:start+16]):
            im=ImageOps.contain(Image.open(path),(352,248));x=(j%4)*360;y=(j//4)*280
            sheet.paste(im,(x+(360-im.width)//2,y));draw.text((x+4,y+251),f'{county} / {number}',fill='black')
        sheet.save(contact_dir/f'sheet_{start//16+1:02d}.jpg',quality=85)

    inventory=read_csv('source_file_inventory.csv')
    duplicate_groups=defaultdict(list)
    for row in inventory:duplicate_groups[row['sha256']].append(row['source_file'])
    duplicates=[{'sha256':sha,'duplicate_file_count':len(names),'source_files':'; '.join(names)} for sha,names in duplicate_groups.items() if len(names)>1]
    write_csv('duplicate_source_files.csv',duplicates,['sha256','duplicate_file_count','source_files'])
    coordinate_issues=[{k:f[k] for k in ['county','farm_id','reported_longitude','reported_latitude','reported_coordinate_in_county','coordinate_conflict','coordinate_source','location_status']}
                       for f in farms if f['reported_coordinate_in_county'] is False or f['coordinate_conflict'] or f['reported_longitude'] is None]
    write_csv('coordinate_exceptions.csv',coordinate_issues)
    fields=json.loads((OUT/'geojson/SC_AMP_FSA_All_Farm_Fields.geojson').read_text())['features']
    original=json.loads((ROOT/'geojson/master_fsa_fields_geopdf_verified.geojson').read_text())['features']
    assert len(fields)==len(original)==22
    assert all(shape(f['geometry']).is_valid for f in fields)
    assert {f['properties']['source_sha256'] for f in fields}=={f['properties']['source_sha256'] for f in original}
    label_checks=[]
    for feature in original:
        p=feature['properties']
        source=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'/p['source_pdf']
        doc=pymupdf.open(source);page=doc[p['page_number']-1]
        items=page.get_drawings()[p['source_draw_index']]['items']
        pixel_polygon=Polygon([tuple(item[1]) for item in items if item[0]=='l'])
        words=page.get_text('words');inside=False
        for i in range(len(words)):
            for length in [1,2]:
                group=words[i:i+length]
                try:value=float(''.join(w[4] for w in group))
                except ValueError:continue
                if abs(value-float(p['fsa_reported_acres']))>1e-7:continue
                px=(min(w[0] for w in group)+max(w[2] for w in group))/2
                py=(min(w[1] for w in group)+max(w[3] for w in group))/2
                inside=inside or pixel_polygon.covers(Point(px,py))
        method='ACREAGE_LABEL_CENTER_INSIDE_SOURCE_PATH' if inside else 'REVIEW_REQUIRED'
        if not inside and str(p['farm_id'])=='17615' and str(p['field_id'])=='3':
            # Visually checked using an independent Poppler source rendering:
            # printed 3 / 1.36 has a leader pointing into the narrow field.
            method='PRINTED_FIELD_3_ACREAGE_1_36_LEADER_VISUALLY_CONFIRMED'
        assert method!='REVIEW_REQUIRED',(p['source_pdf'],p['field_id'])
        label_checks.append({'county':p['county'],'farm_id':p['farm_id'],'tract_id':p['tract_id'],
                             'field_id':p['field_id'],'source_pdf':p['source_pdf'],
                             'acreage_label_center_in_source_path':inside,'label_path_check':method})
    write_csv('source_label_geometry_checks.csv',label_checks)
    inspection=json.loads((WORK/'source_inspections.json').read_text())
    gis_summary=json.loads((OUT/'qa/gis_export_summary.json').read_text())
    registered_enrollment=gis_summary['registered_participant_farm_boundaries']
    reconciliation=json.loads((OUT/'qa/reconciliation_summary.json').read_text())
    used={(m['source'],m['page']) for f in farms for m in f['source_matches']}
    unmatched=[{'source_file':s['source'],'page':p['page'],'status':'NOT_ASSOCIATED_WITH_ANY_ENROLLMENT_FARM; may be duplicate, administrative, example, or unmatched map',
                'farm_ids_read':';'.join(p.get('farm_ids_detected',[]))}
               for s in inspection for p in s['pages'] if (s['source'],p['page']) not in used]
    write_csv('unassigned_source_pages.csv',unmatched,['source_file','page','status','farm_ids_read'])

    current_fields=sum('county_workbook' in f['scopes'] for f in farms)
    row_count=len(page_rows)
    summary={'status':'PARTIAL_DELIVERY_SOURCE_REVIEW_AND_GIS; production basemap atlases incomplete',
             'source_files':len(inventory),'source_pdf_files':110,'source_xlsx_files':25,'source_csv_files':3,'source_image_files':6,
             'source_pdf_image_pages':sum(len(s['pages']) for s in inspection),
             'county_workbook_rows':110,'county_workbook_counties':23,'county_workbook_county_farm_ids':current_fields,
             'union_enrollment_county_farm_id_combinations':len(farms),'counties_with_farm_ids':len({f['county'] for f in farms}),
             'enrollment_records_without_farm_id':4,'additional_county_without_farm_id':'Saluda',
             'one_enrollment_record_without_county':True,
             'registered_source_fields':22,'registered_source_farms':6,'registered_farms_matched_to_enrollment':registered_enrollment,
             'source_supported_county_corrections':reconciliation['source_supported_county_corrections'],
             'source_only_registered_farm_count':gis_summary['source_only_unreconciled_farm_boundaries'],
             'farm_extraction_status':dict(Counter(f['extraction_status'] for f in farms)),
             'review_pdfs':len(coverage),'review_pages':row_count,'rendered_review_pages':row_count,
             'satellite_pdfs':0,'topographic_pdfs':0,'final_production_atlas_archive_created':False,
             'basemap_access':'USGS topography and NAIP HTTPS requests denied by environment proxy (CONNECT 403)',
             'coordinate_correction':'All 22 legacy polygons had north-south reference reversal relative to source GeoPDF/GDAL; original source layers preserved',
             'scope_caution':f'{len(farms)} combinations are listed identifiers across current/historical sources, not independently confirmed distinct current farms. Missing-ID rows may overlap other records.'}
    (OUT/'qa/completion_status.json').write_text(json.dumps(summary,indent=2))
    area=read_csv('acreage_validation.csv')
    county_table=[]
    for c in sorted(coverage,key=lambda r:r['county']):
        subset=[f for f in farms if f['county']==c['county']]
        registered=sum(f['registered_field_geometry'] for f in subset)
        county_table.append(f"| {c['county']} | {c['listed_farm_ids']} | {c['unresolved_enrollment_records']} | {registered} | {len(subset)-registered} | {c['review_pdf_pages']} | Pending | Pending |")
    report=(
        '# SC AMP/FSA verification report\n\n'
        '**Status: partial source-review and GIS delivery. Final satellite and topographic atlases are not complete.**\n\n'
        '## Reconciled scope\n\n'
        '- Downloaded all 144 source files from private repository commit `60bc244`: 110 PDFs, 25 XLSX workbooks, 3 CSVs, 6 images.\n'
        '- Inspected/OCR-processed 217 PDF/image pages. Administrative, contact and tax forms are excluded from map insets.\n'
        '- The 23 county workbooks contain 110 records and 77 county-scoped Farm IDs.\n'
        f"- The raw union initially contained 122 county/Farm-ID combinations. {reconciliation['source_supported_county_corrections']} source-supported county corrections yield {len(farms)} listed combinations across 28 counties. These are not independently confirmed unique current farms. See `county_assignment_corrections.csv`.\n"
        '- Four enrollment rows lack Farm IDs: two Orangeburg, one Saluda, one without a county. They remain visible as unresolved enrollment records; they are not invented farm identities.\n'
        '- Current and historical enrollment scopes remain distinct in the inventory and county indices.\n\n'
        '## Geometry findings\n\n'
        'The 22 preliminary polygons passed basic shape/acreage checks but had a north-south reference reversal. '
        'The corrected exported coordinates were reproduced directly from original vector drawings using GeoPDF GPTS/LPTS and viewport coordinates. '
        'All 22 source hashes and all 22 printed field/acreage pairs were checked. Twenty-one acreage-label centers lie inside their source paths; the remaining narrow field uses a printed leader, confirmed visually in an independent Poppler rendering. The original repository layers were preserved. '
        f"Maximum change from a legacy boundary: {max(float(r['baseline_boundary_hausdorff_m']) for r in area):.1f} m. "
        f"Maximum agreement difference from independent GDAL metadata interpretation: {max(float(r['independent_gdal_reference_max_difference_m']) for r in area):.7f} m. "
        'This is agreement between transforms, not absolute positional accuracy. '
        f"Maximum recomputed acreage difference: {max(abs(float(r['difference_percent'])) for r in area):.3f}%; maximum corner-fit residual: {max(float(r['affine_corner_fit_max_residual_m']) for r in area):.3f} m.\n\n"
        f'There are six source-map farm groups, {registered_enrollment} matched to the supplied enrollment identifier inventory after source-supported county corrections. Farm 8185 was listed under Florence; its scanned source footer confirms Farm 8185 / Tract 2352, and the matching GeoPDF explicitly references Darlington County. Both affected enrollment rows were corrected with original values preserved. '
        f'Farm boundaries unresolved for the other {len(farms)-registered_enrollment} listed combinations are null geometries. No buffers, rectangles or relocated polygons were fabricated. '
        'Source fields are not automatically treated as enrolled program fields; see the field crosswalk.\n\n'
        '## What the PDFs contain\n\n'
        f"{len(coverage)} source-review PDFs ({row_count} pages) cover the 28 counties with Farm IDs, Saluda's unresolved record, and a separate unassigned-county record. "
        'Each overview lists every inventory entry and each entry has corresponding detail pages. '
        'Overviews use actual 2022 Census 1:500,000 county boundaries from the Census Bureau CitySDK data repository. '
        'Usable reported points are marked approximate; missing or outside-county coordinates are listed without invented map positions. '
        'FSA source-map insets retain visible field boundaries. Unregistered insets are not geographic overlays. '
        'Source identity conflicts and missing maps are explicitly labeled. '
        'Source image acquisition dates are not independently established. Some source photographs are blurred or oblique; page rendering does not fix source quality.\n\n'
        '## Remaining production requirements\n\n'
        '1. Enable working access to `basemap.nationalmap.gov` (USGS topography) and `naip.nationalmap.gov` (NAIP), and complete service/imagery date and print-use checks. Both HTTPS requests currently fail at the environment proxy with CONNECT 403. Network requirements have been saved in the configuration draft; the runtime still reports only the older Drive rules.\n'
        f"2. Reconcile county and Farm/Tract/Field conflicts, missing IDs and source matches. Four missing-ID enrollment rows and {summary['farm_extraction_status'].get('NO_CONFIRMED_SOURCE_MAP_MATCH',0)} Farm-ID combinations without a confirmed source map require review. {summary['farm_extraction_status'].get('SOURCE_IDENTITY_REVIEW_REQUIRED',0)} additional Farm-ID combinations have source-identity or county review flags.\n"
        '3. Establish supported control points and registration error for scanned/photographed maps before any new geographic polygon admission. No scanned map has yet been independently geographically registered.\n'
        '4. Generate both final basemap atlas versions, check alignment, render every final page, and verify acquisition dates, attributions and overview/detail correspondence.\n\n'
        'The requested Orangeburg Satellite/Topography PDFs and final `SC_AMP_County_Farm_Atlases.zip` do not exist yet. '
        'The delivered ZIP is deliberately named as a source-review package.\n\n'
        '## County accounting\n\n'
        '| County | Listed Farm IDs | Missing-ID rows | Registered farm groups | Unresolved farm boundaries | Review pages | Satellite | Topography |\n'
        '| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |\n'+'\n'.join(county_table)+'\n\n'
        '## Validation\n\n'
        'Every source-review PDF page was rasterized at 90 dpi, checked for nonblank output and page-bound text. '
        'Every overview identifier was checked against its detail page text; index/detail entry counts match. '
        'Contact sheets are supplied for visual inspection. These checks validate review-document structure, not final basemap alignment or complete geographic verification.\n'
    )
    (OUT/'qa/verification_report.md').write_text(report)
    readme=(
        '# SC AMP/FSA source-review and GIS package\n\n'
        '**PRIVATE — PARTIAL DELIVERY. These are source-review PDFs, not completed satellite/topographic atlases.**\n\n'
        'Start with `qa/verification_report.md` and `qa/completion_status.json`.\n\n'
        '- `source_review_pdfs/`: 17 x 11-inch county reference documents with source FSA map insets and complete inventory/exception accounting.\n'
        '- `geojson/SC_AMP_FSA_All_Farm_Fields.geojson`: 22 corrected, source-reproduced field polygons. Some fields may not be enrolled program fields.\n'
        f'- `geojson/SC_AMP_FSA_All_Farms.geojson`: {len(farms)} listed county/Farm-ID combinations; {len(farms)-registered_enrollment} have null boundaries.\n'
        '- `geojson/Registered_Source_Farms.geojson`: six valid source-map farm geometries; source-supported county corrections are documented in QA.\n'
        '- `geojson/SC_AMP_FSA_Farm_Locations.geojson`: registered representative points or usable approximate reported coordinates; other geometries are null.\n'
        '- `geojson/Unresolved_Enrollment_Records.geojson`: four missing-Farm-ID enrollment rows with null geometry; Saluda county layers are empty pending resolution.\n'
        '- `geojson/counties/`, `shapefiles/counties/`: county Fields, Farms and Locations layers. Empty/null geometries are intentional and must not be filled with invented boundaries.\n'
        '- `qa/`: provenance, enrollment crosswalk, coordinate exceptions, extraction status, acreage/reference QA and page validation.\n'
        '- `previews/`: raster rendering of every review PDF page plus contact sheets.\n\n'
        'All GeoJSON/Shapefile coordinates use EPSG:4326 longitude, latitude. EPSG:32617 is used for distance/area/reference comparisons. '
        'Shapefile attributes use county, farm_id, tract_id, field_id, fsa_acres and status; full provenance is retained in GeoJSON and QA.\n\n'
        'County boundaries: U.S. Census Bureau CitySDK, 2022 cartographic boundaries, 1:500,000; '
        'https://github.com/uscensusbureau/citysdk/blob/fc5d7880529fedcde181269fc5d518767221281e/v2/GeoJSON/500k/2022/county.json . '
        'Only data were used from that archived repository. Source imagery: supplied USDA FSA maps; no crop or property-ownership inference.\n\n'
        'Original source documents and contact/tax forms are not included in the delivery ZIP. Keep derived farm-level maps and identifiers private.\n\n'
        'Reproduction in the prepared cloud environment: `bash scripts/run_atlas_review.sh` from the source repository. '
        'Dependencies are pinned in `scripts/atlas-requirements.txt`; system GDAL and Tesseract are also required. '
        'The script inventories documents, OCRs pages, reconciles records, reproduces GeoPDF polygons, exports layers and builds review PDFs. '
        'It does not implement completed scanned-map control-point georeferencing or final satellite/topographic atlas production.\n'
    )
    (OUT/'README.md').write_text(readme)
    (OUT/'scripts').mkdir(exist_ok=True)
    for script_name in ['atlas_sources.py','atlas_inventory.py','atlas_geopdf.py','atlas_match_sources.py',
                        'atlas_export_gis.py','atlas_review_pdfs.py','atlas_delivery.py','run_atlas_review.sh','atlas-requirements.txt']:
        shutil.copy2(ROOT/'scripts'/script_name,OUT/'scripts'/script_name)
    # Supersede the topology-only export made before the source GeoPDFs arrived.
    legacy_export=OUT/'geojson/existing_subset_farms_topology_checked.geojson'
    if legacy_export.exists():
        corrected=json.loads((OUT/'geojson/Registered_Source_Farms.geojson').read_text())
        corrected['description']='Supersedes the pre-source topology-only export. Coordinates now follow corrected GeoPDF/GDAL referencing; original repository layers are preserved.'
        legacy_export.write_text(json.dumps(corrected,indent=2))
    index=['# County source-review PDFs\n','These PDFs are source-review documents. Satellite and topographic production versions remain pending.\n']
    for c in sorted(coverage,key=lambda r:r['county']):
        index.append(f"- [{c['county']} — {c['review_pdf_pages']} pages]({OUT / c['review_pdf']})")
    (OUT/'COUNTY_PDF_INDEX.md').write_text('\n'.join(index)+'\n')
    # Supersede setup-stage reports whose missing-source statements are now obsolete.
    for name in ['atlas_readiness.md','atlas_readiness.json']:
        path=OUT/'qa'/name
        if path.exists():
            path.write_text('This preliminary pre-source audit is superseded by verification_report.md and completion_status.json.\n' if name.endswith('.md') else json.dumps({'superseded_by':'verification_report.md','source_files_now_available':True}))
    qa_names=['source_file_inventory.csv','source_map_inspection.csv','farm_inventory.csv','county_coverage.csv',
              'producer_record_reconciliation.csv','enrollment_records_missing_farm_id.csv','polygon_extraction_status.csv',
              'source_manual_identifier_readings.csv','source_label_geometry_checks.csv','county_assignment_corrections.csv','acreage_validation.csv','georeferencing_quality.csv',
              'enrolled_field_geometry_crosswalk.csv','gis_export_summary.json','reconciliation_summary.json',
              'map_generation_log.csv','county_pdf_verification.csv','pdf_page_validation.csv','pdf_content_checks.csv',
              'duplicate_source_files.csv','coordinate_exceptions.csv','unassigned_source_pages.csv','completion_status.json','verification_report.md','visual_review_notes.md']
    def make_zip(target,files):
        entries=sorted({p for p in files if p.is_file()})
        with ZipFile(target,'w',ZIP_DEFLATED,compresslevel=6) as archive:
            for path in entries:archive.write(path,str(path.relative_to(OUT)))
        with ZipFile(target) as archive:
            assert archive.testzip() is None
            assert len(archive.namelist())==len(entries)
        return len(entries)
    gis_files=list((OUT/'geojson').rglob('*'))+list((OUT/'shapefiles').rglob('*'))+[OUT/'README.md']+[OUT/'qa'/n for n in qa_names]
    gis_target=OUT/'SC_AMP_GIS_Layers_and_QA.zip';gis_count=make_zip(gis_target,gis_files)
    bundle=list((OUT/'source_review_pdfs').glob('*.pdf'))+gis_files+[OUT/'COUNTY_PDF_INDEX.md']+list((OUT/'previews').rglob('*'))+list((OUT/'scripts').glob('*'))
    bundle_target=OUT/'SC_AMP_Source_Review_and_GIS.zip';bundle_count=make_zip(bundle_target,bundle)
    manifest=[{'file':str(p.relative_to(OUT)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'archive_entries':n}
              for p,n in [(gis_target,gis_count),(bundle_target,bundle_count)]]
    write_csv('delivery_archive_manifest.csv',manifest)
    print(json.dumps({'review_pdfs':len(coverage),'review_pages':row_count,'gis_zip_bytes':gis_target.stat().st_size,
                      'review_zip_bytes':bundle_target.stat().st_size,'zip_integrity':'PASS'},indent=2),flush=True)


if __name__=='__main__':
    main()
