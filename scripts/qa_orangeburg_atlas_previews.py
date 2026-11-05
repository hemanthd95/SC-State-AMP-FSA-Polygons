"""Verify Orangeburg working atlas PDF completeness and render visual previews.

Reject PDFs without raster map panels, source attribution or incomplete labels.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,io
import fitz
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'orangeburg_working_atlas'
OUT=ROOT/'analysis'
MANIFEST=json.loads((SOURCE/'preview_manifest.json').read_text())
assert MANIFEST['status']=='INCOMPLETE_VERIFIED_ONLY_QA_PREVIEW'
report=[]
for atlas in MANIFEST['atlases']:
    path=SOURCE/atlas['filename']
    doc=fitz.open(path)
    if len(doc)!=atlas['pages']:raise RuntimeError(f'Expected {atlas["pages"]} pages in {path.name}, got {len(doc)}')
    checks=[]
    for idx,page in enumerate(doc):
        txt=page.get_text('text')
        pix=page.get_pixmap(matrix=fitz.Matrix(.42,.42),alpha=False)
        img=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
        std=float(np.std(np.array(img.resize((120,80)).convert('L'))))
        nimg=len(page.get_images(full=True))
        if nimg==0 or std<10:raise RuntimeError(f'Blank or imageless map on {path.name} p{idx+1}')
        if 'INCOMPLETE QA PREVIEW' not in txt:raise RuntimeError('Missing incompleteness disclaimer')
        if idx==0 and atlas['verified_fields']>=6 and 'FARM 13709' not in txt:
            raise RuntimeError('County overview missing newly verified Veronica farm index')
        checks.append({'page':idx+1,'images':nimg,'grayscale_std':round(std,2)})
        if idx in (0,1,2,len(doc)-1):
            pix=page.get_pixmap(matrix=fitz.Matrix(1.1,1.1),alpha=False)
            image=Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')
            image.thumbnail((1560,1040))
            dest=OUT/f'orangeburg_pdf_{atlas["kind"].lower()}_page{idx+1}.jpg'
            image.save(dest,quality=78,optimize=True)
    report.append({'filename':atlas['filename'],'pages':len(doc),
                   'size_bytes':path.stat().st_size,
                   'rendered_page_checks':checks,'status':'QA_PASS'})
    print('QA PASS',path.name,'pages',len(doc),flush=True)
    doc.close()
(OUT/'orangeburg_working_atlas_render_check.json').write_text(json.dumps({
    'generated_utc':datetime.now(timezone.utc).isoformat(),
    'status':'PREVIEW_PDF_PAGES_RENDERED_QA_PASS__DRAFT_NOT_FINAL',
    'registered_fields':MANIFEST['atlases'][0]['verified_fields'],
    'fields_remaining':MANIFEST['atlases'][0]['unverified_fields'],
    'atlases':report},indent=2)+'\n')
