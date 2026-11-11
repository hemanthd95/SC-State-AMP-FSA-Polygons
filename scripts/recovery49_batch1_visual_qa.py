#!/usr/bin/env python3
"""Render map PDFs from published Batch 1 ZIP to inspect geography, scale,
road labels and source-field visibility. Does not modify GIS boundaries.
"""
import io,zipfile,json
from pathlib import Path
import fitz
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1]
zip_path=ROOT/"deliverables/AMP_Batch1_Five_Farmer_GIS_20261111.zip"
OUT=ROOT/"analysis/recovery49_20261111/batch1_visual_qa"
OUT.mkdir(parents=True,exist_ok=True)
z=zipfile.ZipFile(zip_path)
names=z.namelist()
sections=["L-Bright Jr., Charles","L-Gadson, Joseph","L-Cobbs, Arthur","L-Summers, Jasper","L-Berry, Margaret"]
report=[]
views=[]
for farmer in sections:
 pdfs=[p for p in names if p.endswith("-FieldMap.pdf") and ("/"+farmer+"/") in p]
 county=[p for p in names if p.endswith("-CountyMap.pdf") and ("/"+farmer+"/") in p]
 shps=[p for p in names if p.endswith(".shp") and ("/"+farmer+"/") in p]
 assert len(pdfs)==1 and len(county)==1 and len(shps)==1,(farmer,pdfs,county,shps)
 for kind,path in [("field",pdfs[0]),("county",county[0])]:
  doc=fitz.open(stream=z.read(path),filetype="pdf")
  assert doc.page_count>=1
  for index in range(doc.page_count):
   page=doc[index]
   assert page.rect.width==612 and page.rect.height==792
   pix=page.get_pixmap(matrix=fitz.Matrix(1.2,1.2),colorspace=fitz.csRGB,alpha=False)
   img=Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
   png=OUT/(farmer.replace(" ","_").replace(",","") + "_"+kind+f"_p{index+1}.jpg")
   img.save(png,quality=82,optimize=True)
   report.append(dict(farmer=farmer,kind=kind,page=index+1,render=str(png.relative_to(ROOT)),dimensions=img.size))
   # Contact sheet thumbnails for rapid visual QA
   thumbnail=img.copy();thumbnail.thumbnail((240,320))
   cell=Image.new("RGB",(260,360),"white")
   cell.paste(thumbnail,((260-thumbnail.width)//2,3))
   title=farmer.replace("L-","")[:22]+" "+kind+str(index+1)
   ImageDraw.Draw(cell).text((8,330),title,fill="black")
   views.append(cell)
   print("VISUAL_RENDER",farmer,kind,index+1,img.size,flush=True)
   if kind=="county":break
cols=4;rows=(len(views)+cols-1)//cols
sheet=Image.new("RGB",(cols*260,rows*360),(234,234,234))
for i,v in enumerate(views):sheet.paste(v,((i%cols)*260,(i//cols)*360))
sheet.save(OUT/"Five_Farmer_Map_Contact_Sheet.jpg",quality=89,optimize=True)
(OUT/"rendered_map_index.json").write_text(json.dumps(report,indent=2))
print("VISUAL_QA_PAGES",len(report),flush=True)
