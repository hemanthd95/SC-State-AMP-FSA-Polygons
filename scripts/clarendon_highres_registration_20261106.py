"""Bounded satellite matching for Clarendon FSA pages; no guessed field polygons."""
import json,sys,os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
sys.path.insert(0,str(Path(__file__).resolve().parent))
import next_three_registration as reg
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT=ROOT/'outputs/clarendon_highres_20261106'
OUT.mkdir(parents=True,exist_ok=True)
reg.SRC=SOURCE
reg.OUT=OUT
import orangeburg_registration_pilot as pilot
pilot.SPAN=650.; reg.SPAN=650.
pilot.STEP=440.; reg.STEP=440.
TARGETS=[
 ('Clarendon','6749_6173','Brandon dingle FSAmap.pdf',1,-80.2126811,33.5971605),
 ('Clarendon','6749_6174','Brandon dingle FSAmap.pdf',2,-80.2126811,33.5971605),
 ('Clarendon','6750_6175','Brandon dingle FSAmap.pdf',3,-80.2126811,33.5971605),
 ('Clarendon','9274_646','Bryan Green_FSAmap.pdf',1,-80.3578469,33.6677637),
 ('Clarendon','1375_1022','Christian Richburg_FSA Map.pdf',1,-80.2970765,33.6431756),
 ('Clarendon','3988_4673','John s Tylik Spann_FSA_Map.pdf',1,-80.2965507,33.6429989),
 ('Clarendon','948_2427','Jeremiah Conyers Farm Map.pdf',1,-80.215,33.6522),
 ('Clarendon','497_2476','Rodrick Andrews_FSAmap.pdf',1,-80.1999,33.7072),
 ('Clarendon','1118_2455','Willie Richburg _FSA Map.pdf',1,-80.2965507,33.6429989),
 ('Clarendon','1118_4102','Willie Richburg _FSA Map.pdf',2,-80.2965507,33.6429989),
 ('Clarendon','1568_1083','Everett Rendell FSAmap.pdf',1,-80.4275,33.6404),
 ('Clarendon','3603_8488','Tyreese Riley_FSA Map.pdf',1,-80.3578469,33.6677637),
 ('Clarendon','7832_9276','Christopher Riley FSAmap1.pdf',1,-80.3578469,33.6677637),
 ('Clarendon','9387_8069','Map of Farm 9387 in Clarendon County, South Carolina.pdf',1,-80.2426989,33.3706279),
 ('Clarendon','9231_7908','PashonnaRendell_FSA_Map.pdf',1,-80.4275,33.6404),
]
# TIFF-like scanned JPEG source converted to a temporary PDF for registration.
try:
 from PIL import Image,ImageOps
 f=SOURCE/'Erica Wallace Green_FSA_Map.jpeg'
 im=ImageOps.exif_transpose(Image.open(f)).convert('RGB')
 if im.width>im.height:im=im.rotate(90,expand=True)
 im.save(SOURCE/'_clarendon_erica_source.pdf','PDF',resolution=120)
 TARGETS.append(('Clarendon','9274_662','_clarendon_erica_source.pdf',1,-80.3577212,33.6692034))
except Exception as exc:print('ERICA_SOURCE_CONVERSION_FAILED',str(exc),flush=True)
# Farm 1694 omitted: no matching FSA boundary map in the source archive.
def check(t):
 try:
  r=reg.process(t)
  return r
 except Exception as exc:
  return dict(county=t[0],farm_id=t[1],source_pdf=t[2],source_page=t[3],status='ERROR',error=str(exc))
def main():
 group=sys.argv[1] if len(sys.argv)>1 else 'core'
 if group=='core':targets=[t for t in TARGETS if t[1] in {'6749_6173','6749_6174','6750_6175','1375_1022','3988_4673','948_2427','497_2476','1568_1083'}]
 else:targets=[]
 results=[]
 with ThreadPoolExecutor(max_workers=3) as pool:
  jobs={pool.submit(check,t):t for t in targets}
  for fut in as_completed(jobs):
   r=fut.result();results.append(r)
   print('DONE',r['farm_id'],r['status'],flush=True)
   (OUT/f'registration_{group}_incremental.json').write_text(json.dumps(results,indent=2)+'\n')
 (OUT/f'registration_{group}_results.json').write_text(json.dumps(sorted(results,key=lambda r:r['farm_id']),indent=2)+'\n')
 print('COMPLETE',group,len(results),flush=True)
if __name__=='__main__':main()
