"""Inventory Orangeburg AMP fields and FSA PDF source evidence without guessing geometry.

Run inside the private repository. Write only farm/tract/field identifiers,
source map candidates, PDF spatial-reference checks and coverage flags.
"""
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
import json
import re

import fitz
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
ROSTER=SOURCE/'Producers by County/Orangeburg County_Producers.xlsx'
OUT=ROOT/'analysis/orangeburg_source_inventory.json'
OUT.parent.mkdir(parents=True,exist_ok=True)

def norm(text):
    return re.sub(r'[^a-z0-9]+',' ',str(text or '').lower()).strip()

def numeric(x):
    if x is None:return ''
    if isinstance(x,(int,float)) and float(x).is_integer():
        return str(int(x))
    return str(x).strip()

if not ROSTER.is_file():
    raise FileNotFoundError('Source FSA Orangeburg workbook not present or Git LFS not pulled: '+str(ROSTER))
ws=load_workbook(ROSTER,read_only=True,data_only=True).active
headers=[str(c.value or '') for c in ws[1]]
farms=defaultdict(lambda:{'producer':'','tracts':set(),'field_records':[]})
row_count=0
for row in ws.iter_rows(min_row=2,values_only=True):
    fid=numeric(row[2] if len(row)>2 else None)
    if not fid:continue
    row_count+=1
    e=farms[fid]
    e['producer']=' '.join(str(v or '').strip() for v in row[:2]).strip()
    tract=numeric(row[3] if len(row)>3 else None)
    field=numeric(row[4] if len(row)>4 else None)
    if tract:e['tracts'].add(tract)
    e['field_records'].append({'tract_id':tract,'field_id':field})

pdfs=[]
for pdf in sorted(SOURCE.rglob('*.pdf')):
    if 'Producers by County' in str(pdf) or '_maps' in str(pdf).lower():
        continue
    rel=str(pdf.relative_to(SOURCE))
    entry={'path':rel,'filename':pdf.name}
    try:
        with fitz.open(pdf) as doc:
            entry['pages']=len(doc)
            entry['has_pdf_geographic_viewport']=False
            entry['has_vector_drawings']=False
            text=''
            for page in list(doc)[:3]:
                try:entry['has_pdf_geographic_viewport']|=doc.xref_get_key(page.xref,'VP')[0]!='null'
                except Exception:pass
                try:entry['has_vector_drawings']|=len(page.get_drawings())>0
                except Exception:pass
                text+=' '+page.get_text('text')
            entry['native_text_farm_ids']=list(dict.fromkeys(re.findall(r'\bFarm\s*(?:Number|No\.?|#)?\s*[:\-]?\s*(\d{2,6})\b',text,re.I)))
            entry['native_text_tract_ids']=list(dict.fromkeys(re.findall(r'\bTract\s*(?:Number|No\.?|#)?\s*[:\-]?\s*(\d{2,7})\b',text,re.I)))
            entry['pdf_has_extractable_text']=len(text.strip())>20
    except Exception as exc:
        entry['error']=str(exc)[:160]
    pdfs.append(entry)

for fid,record in sorted(farms.items(),key=lambda pair:int(pair[0]) if pair[0].isdigit() else 999999):
    producer=norm(record['producer'])
    tokens=producer.split()
    first=tokens[0] if tokens else ''
    last=tokens[-1] if tokens else ''
    matches=[]
    for p in pdfs:
        fn=norm(Path(p['filename']).stem)
        fntokens=fn.split()
        score=0
        if fid in p.get('native_text_farm_ids',[]):score+=100
        if set(record['tracts']) & set(p.get('native_text_tract_ids',[])):score+=45
        if last and len(last)>2 and last in fntokens:score+=15
        if first and len(first)>2 and first in fntokens:score+=8
        if last and len(last)>4 and any(SequenceMatcher(None,last,t).ratio()>.79 for t in fntokens):score+=5
        if first and len(first)>4 and any(SequenceMatcher(None,first,t).ratio()>.79 for t in fntokens):score+=3
        if score>=8:
            matches.append({'path':p['path'],'match_score':score,
                'native_geopdf':bool(p.get('has_pdf_geographic_viewport')),
                'pages':p.get('pages',0),'native_text_farm_ids':p.get('native_text_farm_ids',[])})
    matches.sort(key=lambda item:(-item['match_score'],item['path']))
    record['candidate_fsa_pdf_sources']=matches[:7]
    record['match_status']=('STRONG_FARM_ID_OR_TRACT_TEXT' if matches and matches[0]['match_score']>=45 else
                            'FILENAME_CANDIDATE_UNVERIFIED' if matches else 'NO_CLEAR_SOURCE_MAP_MATCH')
    record['tracts']=sorted(record['tracts'])
    record['field_records'].sort(key=lambda x:(x['tract_id'],x['field_id']))

output={
  'county':'Orangeburg','date_utc':datetime.now(timezone.utc).isoformat(),
  'workbook_path':str(ROSTER.relative_to(ROOT)),'workbook_headers':headers,
  'roster_field_rows':row_count,'distinct_farm_ids':len(farms),
  'roster_warning':'County column in source spreadsheet cannot be used alone to confirm physical location',
  'fsa_source_pdf_count':len(pdfs),
  'fsa_source_pdf_native_geopdf_count':sum(bool(p.get('has_pdf_geographic_viewport')) for p in pdfs),
  'farms':dict(sorted(farms.items(),key=lambda x:x[0])),
  'pdf_source_inventory':pdfs,
  'status':'INVENTORY_ONLY_NO_UNVERIFIED_FIELD_GEOMETRIES'
}
OUT.write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n')
print('ORANGEBURG INVENTORY',len(farms),'farms',row_count,'field rows',len(pdfs),'source PDFs')
print('SOURCE MATCHED',sum(bool(f['candidate_fsa_pdf_sources']) for f in farms.values()),'of',len(farms))
print('OUTPUT',OUT)
