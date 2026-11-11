#!/usr/bin/env python3
"""Render ONLY detected aerial map pages for Batch2. Page image heuristic
excludes scanned forms/tax records; output stays in private research repo.
Extracts source FSA Farm/Tract metadata when searchable.
"""
from pathlib import Path
import fitz,io,math,re,json
import numpy as np
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT=ROOT/"analysis/recovery49_20261111/batch2/source_page_previews"
OUT.mkdir(parents=True,exist_ok=True)
SOURCES=[
 ("Joe_Hilliard_primary","Joe Hillard_FSA_Map.pdf"),
 ("Joe_Hilliard_alternate","Joe_Hillard_FSA_Map.pdf"),
 ("Calvin_Blair","Calvin_Blair_FSA_Map.pdf"),
 ("Tywone_Hilliard","Tywone Hillard_FSA_Map.pdf"),
 ("Timothy_Hilliard_alternate","Timothy J Hilliard_FSA_Map.pdf"),
 ("Christine_Berry_Zeigler","Christine Berry Zeigler_FSA Map.pdf")
]
records=[];frames=[]
for name,pdf in SOURCES:
 path=SRC/pdf
 if not path.exists():
  records.append(dict(farmer_source=name,source=pdf,status="MISSING_PDF"))
  continue
 d=fitz.open(path)
 for i,p in enumerate(d):
  # Low res sufficient for photo fraction gating
  pix=p.get_pixmap(matrix=fitz.Matrix(1.2,1.2),colorspace=fitz.csRGB,alpha=False)
  im=Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
  a=np.asarray(im)
  h,w=a.shape[:2]
  crop=a[max(0,int(.1*h)):min(h,int(.72*h)),int(.06*w):int(.94*w)]
  g=crop[...,1].astype("int16");r=crop[...,0].astype("int16");b=crop[...,2].astype("int16")
  green=((g-r>7)&(g-b>1)&(g>45)&(g<215)).mean()
  color=((crop.max(axis=2)-crop.min(axis=2))>22).mean()
  s=p.get_text()
  ids=re.findall(r'(Farm|Tract)\s*(\d{2,6})',s,flags=re.I)
  # FSA map pages have vegetation and high color occupancy. Strong image
  # threshold is conservative: retain candidates with 5% green.
  retained=green>.04 and color>.10
  row=dict(pdf=pdf,source_alias=name,page=i+1,pages_total=len(d),
      green_fraction=round(float(green),4),color_fraction=round(float(color),4),
      parsed_ids=ids,rendered_as_map=bool(retained))
  if retained:
   # redact only irrelevant footer remains in image? Crop to aerial region,
   # deliberately excluding signature/tax forms and PDF bottom documentation.
   image=Image.fromarray(a[:int(.81*h),:,:])
   dest=OUT/f"{name}_p{i+1}_FSA_aerial_crop.jpg"
   image.save(dest,quality=85,optimize=True)
   thumb=image.copy();thumb.thumbnail((390,400))
   panel=Image.new("RGB",(420,460),"white")
   panel.paste(thumb,((420-thumb.width)//2,10))
   ImageDraw.Draw(panel).text((14,416),f"{name} page{i+1}",fill="black")
   frames.append(panel)
   row["image_file"]=dest.name
  records.append(row)
  print("MAP_PAGE_QA",name,i+1,"green",row["green_fraction"],"color",row["color_fraction"],"retain",retained,"IDs",ids,flush=True)
 d.close()
if frames:
 col=3;rows=math.ceil(len(frames)/col)
 sheet=Image.new("RGB",(col*420,rows*460),"#EDEDED")
 for i,img in enumerate(frames):sheet.paste(img,((i%col)*420,(i//col)*460))
 sheet.save(OUT/"Batch2_Source_Map_Contact_Sheet.jpg",quality=85,optimize=True)
(OUT/"FSA_source_page_image_filter_QA.json").write_text(json.dumps(records,indent=2)+"\n")
print("SOURCE_AERIAL_PREVIEWS",len(frames),flush=True)
