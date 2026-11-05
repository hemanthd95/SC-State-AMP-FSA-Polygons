"""Find requested farm/tract maps within alternate 21-page Veronica FSA PDF.

Store only source page identifiers and map-preview images; avoid exposing
personal text extracted from unrelated FSA producer documents.
"""
import json,re,subprocess,shutil
from pathlib import Path
import fitz
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT=ROOT/'analysis'
p=SOURCE/'Vronica Hodges_FSA_Map.pdf'
if not p.is_file():raise FileNotFoundError(str(p))
if not shutil.which('tesseract'):raise RuntimeError('tesseract OCR unavailable')
targets={'13709','45508','45511','45512','45513','45514'}
report={'source_pdf':p.name,'target_farm_id':'13709','target_tract_ids':sorted(targets-{'13709'}),'pages':[],'status':'OCR_SOURCE_ID_REVIEW_ONLY'}
with fitz.open(p) as doc:
    for i,page in enumerate(doc):
        pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),colorspace=fitz.csGRAY,alpha=False)
        proc=subprocess.run(['tesseract','stdin','stdout','-l','eng','--psm','11'],
            input=pix.tobytes('png'),stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
            timeout=40,check=True)
        txt=proc.stdout.decode('utf-8','replace')
        farms=list(dict.fromkeys(re.findall(r'\bFarm\s*(?:ID|#|No)?\s*:?\s*(\d{3,6})\b',txt,re.I)))
        tracts=list(dict.fromkeys(re.findall(r'\bTract\s*(?:ID|#|No)?\s*:?\s*(\d{3,7})\b',txt,re.I)))
        found=bool(set(farms+tracts)&targets)
        row={'pdf_page':i+1,'farm_ids_ocr':farms,'tract_ids_ocr':tracts,'matches_target_id':found}
        report['pages'].append(row)
        if found:
            name=OUT/f'orangeburg_veronica_alt21_match_page{i+1:02d}.jpg'
            page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),alpha=False).save(name,jpg_quality=83)
        print('ALT VERONICA',i+1,'Farm',farms,'Tract',tracts,'TARGET',found,flush=True)
report['source_pages_matching_requested_id']=[x['pdf_page'] for x in report['pages'] if x['matches_target_id']]
(OUT/'orangeburg_veronica_alt21_page_identifier_audit.json').write_text(json.dumps(report,indent=2)+'\n')
print('MATCHING PAGES:',report['source_pages_matching_requested_id'],flush=True)
