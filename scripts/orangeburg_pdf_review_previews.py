"""Create private preview sheets of original Orangeburg FSA map pages.

These are NOT georeferenced and cannot be used as accepted farm polygons.
"""
from pathlib import Path
from io import BytesIO
from PIL import Image, ImageDraw
import fitz, json, re

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
DATA=json.loads((ROOT/'analysis/orangeburg_source_inventory.json').read_text())
OUT=ROOT/'analysis/orangeburg_fsa_review_previews'
OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for fid,f in sorted(DATA['farms'].items(),key=lambda kv:int(kv[0])):
    if fid=='14043':continue
    sources=f.get('candidate_fsa_pdf_sources') or []
    if not sources:continue
    pdf=SRC/sources[0]['path']
    ims=[]
    with fitz.open(pdf) as doc:
        for page in list(doc)[:2]:
            factor=min(1.75,1350/max(page.rect.width,page.rect.height))
            pix=page.get_pixmap(matrix=fitz.Matrix(factor,factor),
                                colorspace=fitz.csRGB,alpha=False)
            img=Image.open(BytesIO(pix.tobytes('png'))).convert('RGB')
            ims.append(img)
    if not ims:continue
    w=max(i.width for i in ims)
    sheet=Image.new('RGB',(w,sum(i.height for i in ims)+65+12*len(ims)),'white')
    dr=ImageDraw.Draw(sheet)
    dr.text((18,12),f'FARM {fid}  |  {f["producer"]}  |  {f["match_status"]}',fill='#12334c')
    dr.text((18,35),f'UNREGISTERED SOURCE PREVIEW ONLY -- {pdf.name[:90]}',fill='#c43c3c')
    y=65
    for p,img in enumerate(ims,1):
        sheet.paste(img,((w-img.width)//2,y))
        y+=img.height+12
    dest=OUT/f'orangeburg_fsa_farm_{fid}.jpg'
    sheet.save(dest,quality=77,optimize=True)
    rows.append({'farm_id':fid,'status':f['match_status'],
                 'source_pdf':sources[0]['path'],
                 'preview':str(dest.relative_to(ROOT)),
                 'pages_shown':len(ims)})
    print('PREVIEW',fid,'pages',len(ims),'size',dest.stat().st_size,flush=True)
(OUT/'review_manifest.json').write_text(json.dumps({
    'status':'UNREGISTERED_MAP_PREVIEWS_FOR_MANUAL_QA_ONLY',
    'excluded_farm_id':'14043',
    'farms':rows
},indent=2)+'\n')
print('FINISHED',len(rows),flush=True)
