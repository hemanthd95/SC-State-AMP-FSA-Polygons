#!/usr/bin/env python3
"""Batch2: inventory original source PDFs (page counts, sizes, searchable labels).
No images or private producer forms exported by this inventory step.
"""
from pathlib import Path
import fitz,json,re
root=Path(__file__).resolve().parents[1]
src=root/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
out=root/"analysis/recovery49_20261111/batch2"
out.mkdir(parents=True,exist_ok=True)
cases=[
 ("Joe Hilliard","Joe Hillard_FSA_Map.pdf","13859/45814/20"),
 ("Calvin Blair","Calvin_Blair_FSA_Map.pdf","3603/848/3"),
 ("Tywone Hilliard","Tywone Hillard_FSA_Map.pdf","1064/?/?;3826/?/?"),
 ("Christine Berry Zeigler","Christine Berry Zeigler_FSA Map.pdf","1271/469/1")
]
results=[]
for name,file,target in cases:
 p=src/file
 x=dict(name=name,source=file,enrolled_target=target,pages=[])
 if not p.exists():x["status"]="MISSING_SOURCE"
 else:
  d=fitz.open(p);x["status"]="FOUND_SOURCE";x["count"]=len(d)
  for i,page in enumerate(d):
   s=page.get_text("text")
   tokens=re.findall(r'(?:Farm|Tract|Field|Acres)[^\n]{0,35}',s,re.I)
   x["pages"].append(dict(index=i+1,pts_wh=[round(page.rect.width),round(page.rect.height)],
       image_count=len(page.get_images()),text_len=len(s),
       farm_tract_label_tokens=tokens[:20]))
  d.close()
 results.append(x)
 print("SOURCE",name,"pages",x.get("count"),"labels",[(p["index"],p["farm_tract_label_tokens"][:8]) for p in x.get("pages",[])],flush=True)
(out/"batch2_source_page_inventory.json").write_text(json.dumps(results,indent=2)+"\n")
