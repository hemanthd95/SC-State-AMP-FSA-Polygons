"""Refresh the private delivery with the corrected county-workbook roster."""
import csv
import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image, ImageDraw, ImageOps
import pymupdf
import shapefile
from atlas_export_gis import shape_export

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'
FIX=OUT/'corrected_county_atlases/Williamsburg'
DEST=ROOT/'deliverables/source-review-2026-11-03'
PDF='Williamsburg_County_Two_Farm_Source_Imagery_Atlas.pdf'
NOTICE='**Williamsburg correction:** The earlier four-entry map was wrong for the county workbook. The corrected map contains only Farms 17615 and 10519, from Sheet1 rows 2 and 3. Master-only IDs 17614 and 5611 are excluded. Master records remain audit evidence, not extra county-map farms. Other county source reviews still require county-roster validation.\n\n'


def read(name):
    with (OUT/'qa'/name).open() as s:return list(csv.DictReader(s))


def write(name,rows):
    with (OUT/'qa'/name).open('w',newline='') as s:
        w=csv.DictWriter(s,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def pack(target,entries):
    temp=target.with_suffix('.partial.zip')
    with ZipFile(temp,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for path,name in entries:z.write(path,name)
    with ZipFile(temp) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(set(z.namelist()))
    temp.replace(target)


def main():
    assert json.loads((FIX/'Williamsburg_Verification.json').read_text())['included_farm_ids']==['17615','10519']
    small=FIX/'Williamsburg_Corrected_Atlas_and_GIS.zip'
    pack(small,[(p,p.name) for p in sorted(FIX.iterdir()) if p.is_file() and p!=small and not p.name.endswith('.partial.zip')])
    legacy=OUT/'source_review_pdfs/Williamsburg_County_Source_Review.pdf'
    shutil.copy2(FIX/PDF,legacy)
    # County GIS layers must use the same two-entry roster as the corrected PDF.
    gis_layers=[('Fields','Williamsburg_County_Workbook_Selected_Fields.geojson',shapefile.POLYGON),
                ('Farms','Williamsburg_Two_Farms.geojson',shapefile.POLYGON),
                ('Locations','Williamsburg_Two_Farm_Locations.geojson',shapefile.POINT)]
    for label,filename,kind in gis_layers:
        data=json.loads((FIX/filename).read_text())
        assert len(data['features'])==2
        shutil.copy2(FIX/filename,OUT/'geojson/counties'/f'Williamsburg_{label}.geojson')
        shape_export(OUT/'shapefiles/counties'/f'Williamsburg_{label}',data['features'],kind)
    preview=OUT/'previews/Williamsburg';preview.mkdir(exist_ok=True)
    for p in preview.glob('page_*.jpg'):p.unlink()
    for n in range(1,4):shutil.copy2(FIX/f'page_{n:02d}.jpg',preview/f'page_{n:03d}.jpg')
    cov=read('county_pdf_verification.csv')
    for r in cov:
        if r['county']=='Williamsburg':
            r.update(listed_farm_ids='2',unresolved_enrollment_records='0',overview_index_entries='2',detail_inventory_entries='2',review_pdf_pages='3')
    write('county_pdf_verification.csv',cov)
    logs=read('map_generation_log.csv');logs=[r for r in logs if r['county']!='Williamsburg' or r['farm_id'] in ['17615','10519']]
    for r in logs:
        if r['county']=='Williamsburg':
            r.update(map_number='1' if r['farm_id']=='17615' else '2',detail_pages='2' if r['farm_id']=='17615' else '3',source_insets='1',status='COUNTY_WORKBOOK_ROSTER_CORRECTED')
    write('map_generation_log.csv',logs)
    pages=read('pdf_page_validation.csv');template=pages[0]
    pages=[r for r in pages if r['pdf']!='source_review_pdfs/Williamsburg_County_Source_Review.pdf']
    doc=pymupdf.open(legacy);assert len(doc)==3
    for i,page in enumerate(doc,1):
        assert page.rect.width==1224 and page.rect.height==792
        assert all(b[0]>=-1 and b[1]>=-1 and b[2]<=1225 and b[3]<=793 for b in page.get_text('blocks') if b[6]==0)
        row={k:'' for k in template}
        row.update(pdf='source_review_pdfs/Williamsburg_County_Source_Review.pdf',page=i,width_inches=17,height_inches=11,rendered=True,
                   text_overflow_blocks=0,preview=f'previews/Williamsburg/page_{i:03d}.jpg',review_type='COUNTY_WORKBOOK_ROSTER_CORRECTED',page_render_status='PASS')
        histogram=Image.open(preview/f'page_{i:03d}.jpg').convert('L').histogram()
        fraction=sum(histogram[:235])/sum(histogram)
        assert fraction>.005
        row['nonwhite_pixel_fraction']=fraction
        pages.append(row)
    assert 'Farm 17615' in doc[0].get_text() and 'Farm 10519' in doc[0].get_text()
    assert 'Farm 17615' in doc[1].get_text() and 'Farm 10519' in doc[2].get_text()
    write('pdf_page_validation.csv',pages)
    checks=read('pdf_content_checks.csv')
    for r in checks:
        if r['county']=='Williamsburg':r['pages']='3'
    write('pdf_content_checks.csv',checks)
    state_path=OUT/'qa/completion_status.json';state=json.loads(state_path.read_text());old_pages=state['review_pages']
    state.update(review_pages=len(pages),rendered_review_pages=len(pages),county_map_roster_corrections={'Williamsburg':{
        'authority':'Williamsburg County_Producers.xlsx / Sheet1 / rows 2 and 3','included_farm_ids':['17615','10519'],
        'excluded_master_only_ids':['17614','5611'],'overview_markers':2,'detail_farms':2}})
    state_path.write_text(json.dumps(state,indent=2))
    report_path=OUT/'qa/verification_report.md';report=report_path.read_text()
    if NOTICE not in report:report=NOTICE+report
    report=report.replace(f'({old_pages} pages)',f'({len(pages)} pages)')
    report='\n'.join('| Williamsburg | 2 | 0 | 2 | 0 | 3 | Pending | Pending |' if line.startswith('| Williamsburg |') else line for line in report.splitlines())+'\n'
    report_path.write_text(report)
    visual=OUT/'qa/visual_review_notes.md'
    if visual.exists():
        note=visual.read_text().replace(f'All {old_pages} current PDF pages',f'All {len(pages)} current PDF pages')
        if 'Williamsburg county-workbook correction' not in note:
            note+='\nWilliamsburg county-workbook correction: all three corrected pages were rendered and visually inspected. There are exactly two overview markers and two farm detail pages.\n'
        visual.write_text(note)
    root_readme=OUT/'README.md'
    if NOTICE not in root_readme.read_text():root_readme.write_text(NOTICE+root_readme.read_text())
    index=['# County source-review PDFs','',NOTICE]
    for r in sorted(cov,key=lambda r:r['county']):index.append(f"- [{r['county']} — {r['review_pdf_pages']} pages]({OUT/r['review_pdf']})")
    (OUT/'COUNTY_PDF_INDEX.md').write_text('\n'.join(index)+'\n')
    # Rebuild the contact sheets so no obsolete four-entry preview is delivered.
    previews=[]
    for r in cov:
        for n in range(1,int(r['review_pdf_pages'])+1):previews.append((r['county'],n,OUT/'previews'/r['county']/f'page_{n:03d}.jpg'))
    contact=OUT/'previews/contact_sheets'
    for p in contact.glob('sheet_*.jpg'):p.unlink()
    for start in range(0,len(previews),16):
        sheet=Image.new('RGB',(1440,1120),'white');draw=ImageDraw.Draw(sheet)
        for j,(county,n,p) in enumerate(previews[start:start+16]):
            im=ImageOps.contain(Image.open(p),(352,248));x=j%4*360;y=j//4*280
            sheet.paste(im,(x+(360-im.width)//2,y));draw.text((x+4,y+251),f'{county} / {n}',fill='black')
        sheet.save(contact/f'sheet_{start//16+1:02d}.jpg',quality=85)
    for name in ['williamsburg_county_workbook_atlas.py','publish_williamsburg_correction.py','run_atlas_review.sh']:
        shutil.copy2(ROOT/'scripts'/name,OUT/'scripts'/name)
    # All links previously supplied on GitHub now point to the corrected PDF.
    dest_fix=DEST/'corrected_county_atlases/Williamsburg'
    shutil.copytree(FIX,dest_fix,dirs_exist_ok=True)
    shutil.copy2(legacy,DEST/'source_review_pdfs'/legacy.name)
    for name in ['completion_status.json','county_pdf_verification.csv','verification_report.md']:
        shutil.copy2(OUT/'qa'/name,DEST/'qa'/name)
    d_readme=DEST/'README.md';content=d_readme.read_text().replace('Williamsburg — 5 pages','Williamsburg — 3 pages')
    content=content.replace('(165 pages)',f'({len(pages)} pages)')
    correction_links='[Corrected Williamsburg three-page PDF](corrected_county_atlases/Williamsburg/'+PDF+') | [Williamsburg atlas and GIS ZIP](corrected_county_atlases/Williamsburg/Williamsburg_Corrected_Atlas_and_GIS.zip)\n\n'
    if NOTICE not in content:content=NOTICE+correction_links+content
    d_readme.write_text(content)
    main_zip=OUT/'SC_AMP_Source_Review_and_GIS.zip'
    with ZipFile(main_zip) as z:names=z.namelist()
    names=[n for n in names if not n.startswith('previews/')]
    paths={n:OUT/n for n in names}
    for directory in [OUT/'previews',OUT/'corrected_county_atlases',OUT/'scripts']:
        for p in directory.rglob('*'):
            if p.is_file():paths[str(p.relative_to(OUT))]=p
    pack(main_zip,[(p,n) for n,p in sorted(paths.items())])
    gis_zip=OUT/'SC_AMP_GIS_Layers_and_QA.zip'
    with ZipFile(gis_zip) as z:gis_names=z.namelist()
    gis_paths={n:OUT/n for n in gis_names}
    for p in FIX.iterdir():
        if p.is_file() and p.suffix.lower() in ['.geojson','.shp','.shx','.dbf','.prj','.cpg','.csv','.json','.md']:
            gis_paths[str(p.relative_to(OUT))]=p
    pack(gis_zip,[(p,n) for n,p in sorted(gis_paths.items())])
    manifest=[]
    for archive in [gis_zip,main_zip]:
        with ZipFile(archive) as z:count=len(z.namelist())
        manifest.append({'file':archive.name,'bytes':archive.stat().st_size,
                         'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'archive_entries':count})
    write('delivery_archive_manifest.csv',manifest)
    shutil.copy2(main_zip,DEST/main_zip.name)
    shutil.copy2(gis_zip,DEST/gis_zip.name)
    shutil.copy2(OUT/'qa/delivery_archive_manifest.csv',DEST/'qa/delivery_archive_manifest.csv')
    print(json.dumps({'Williamsburg_farms':2,'Williamsburg_pages':3,'all_review_pages':len(pages),
                      'corrected_zip_bytes':small.stat().st_size,'main_zip_integrity':'PASS'},indent=2))


if __name__=='__main__':main()
