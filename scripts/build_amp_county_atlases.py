#!/usr/bin/env python3
"""Generate county overview + detailed field atlas PDFs (provisional where source geometry is missing)."""
import csv
import hashlib
import io
import json
import math
import os
import re
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Polygon as MplPolygon
from PIL import Image
import requests
import shapefile
import fitz
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
PDFDIR = OUT / "county_pdfs"
CACHEDIR = OUT / "_imagery_cache"
QA = OUT / "qa"
for p in [PDFDIR, CACHEDIR, QA]:
    p.mkdir(parents=True, exist_ok=True)

CENSUS = "https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip"
SOURCES = {
    "Satellite": [
        ("USGS NAIP imagery", "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage", "image"),
        ("USGS ImageryOnly", "https://basemap.nationalmap.gov/arcgis/rest/services/USGSImageryOnly/MapServer/export", "map"),
    ],
    "Topography": [
        ("USGS Topo", "https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export", "map"),
    ],
}
COLORS = plt.cm.get_cmap("tab20", 20)
BASEMAP_FAILURES = []
ALL_LOGS = []

def request_bytes(url, params=None, tries=3):
    last = None
    for n in range(tries):
        try:
            r = requests.get(url, params=params, timeout=75, headers={"User-Agent":"SCSU-AMP-FSA-Atlas/1.0"})
            r.raise_for_status()
            if len(r.content) < 200:
                raise ValueError("Small/empty HTTP response")
            return r.content
        except Exception as exc:
            last = exc
            time.sleep(1+n*2)
    raise RuntimeError(f"Could not retrieve map source: {url}: {last}")

def load_counties():
    blob = request_bytes(CENSUS)
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        files = z.namelist()
        def suffix(ext):
            return io.BytesIO(z.read(next(f for f in files if f.lower().endswith(ext))))
        rd = shapefile.Reader(shp=suffix(".shp"), shx=suffix(".shx"), dbf=suffix(".dbf"), encoding="utf-8")
        result = {}
        for rec in rd.iterShapeRecords():
            props = rec.record.as_dict()
            if props.get("STATEFP") != "45":
                continue
            result[props["NAME"]] = shape(rec.shape.__geo_interface__)
        return result

def load_data():
    inv = json.loads((ROOT/"data/farm_inventory_county_spreadsheets.json").read_text())["farms"]
    gj = json.loads((ROOT/"geojson/master_fsa_fields_geopdf_verified.geojson").read_text())
    geoms = defaultdict(list)
    for f in gj["features"]:
        pr = f["properties"]
        geoms[(pr["county"], str(pr["farm_id"]))].append(shape(f["geometry"]))
    return inv, geoms

def load_source_map_links():
    p=ROOT/"data/farm_source_pdf_crosswalk.json"
    if not p.exists():
        return {}
    data=json.loads(p.read_text())
    return {(r["county"],str(r["farm_id"])): r for r in data["crosswalk"]}

def source_reference_image(farm, links):
    record=links.get((farm["county"],str(farm["farm_id"])))
    if not record or not record.get("source_pdf"):
        return None, None
    path=ROOT/record["source_pdf"]
    if not path.is_file():
        print(f"WARNING: Original FSA map absent: {path}",flush=True)
        return None, record
    try:
        if path.suffix.lower()==".pdf":
            with fitz.open(path) as doc:
                if not len(doc):
                    return None,record
                pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.35,1.35),colorspace=fitz.csRGB,alpha=False)
                im=Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
        else:
            im=Image.open(path).convert("RGB")
        if max(im.size)>3500:
            im.thumbnail((3500,3500))
        return im, record
    except Exception as exc:
        print(f"WARNING: Cannot render original FSA source map {path}: {exc}",flush=True)
        return None, record

def make_source_map_appendices(pdf,county,variant,farms,geoms,links,starting_page):
    count=0
    for idx,farm in enumerate(farms):
        if geoms.get((county,str(farm["farm_id"]))):
            continue # Verified geometry is already shown over both basemap types.
        im,record=source_reference_image(farm,links)
        if im is None:
            continue
        fig=plt.figure(figsize=(17,11),facecolor="white")
        add_header(fig,county,variant,f"Original FSA boundary reference  |  farm {idx+1} of {len(farms)}")
        ax=fig.add_axes([0.055,0.19,0.89,0.66])
        ax.imshow(im,interpolation="nearest")
        ax.set_xticks([]);ax.set_yticks([])
        ax.set_title(f"{idx+1:02d}  |  FARM {farm['farm_id']}   |   FSA SOURCE DOCUMENT",fontsize=16,loc="left",pad=10)
        fig.text(0.05,0.125,"VISIBLE FSA FIELD OUTLINES — original source page, NOT spatially registered to the county basemap.",
                 fontsize=12,color="#ac571f",fontweight="bold")
        fig.text(0.05,0.096,"The separate farm detail panel places the reported location on the USGS background. This source page preserves the actual outline visually; do not interpret that point as the field boundary.",fontsize=9,color="#47545a")
        fig.text(0.05,0.076,f"Original document: {Path(record['source_pdf']).name}  |  Record match: {record['match_status']}",fontsize=8,color="#62747b")
        footer(fig,starting_page+count+1,variant,"Original FSA source map (as provided)",True)
        pdf.savefig(fig,dpi=185)
        plt.close(fig)
        im.close()
        count+=1
    return count

def adjusted_bounds(box, min_width=0.02, min_height=0.015, padding=0.17):
    x0, y0, x1, y1 = box
    xc=(x0+x1)/2; yc=(y0+y1)/2
    width=max((x1-x0)*(1+2*padding),min_width)
    height=max((y1-y0)*(1+2*padding),min_height)
    # Provide ample physical lateral space in a wide landscape frame.
    if width < height*1.3:
        width=height*1.3
    if height < width*0.45:
        height=width*0.45
    return (xc-width/2, yc-height/2, xc+width/2, yc+height/2)

def basemap(extent, variant, size=(1300,850)):
    key=hashlib.sha256((variant+repr(tuple(round(x,7) for x in extent))+repr(size)).encode()).hexdigest()[:22]
    path=CACHEDIR/(key+".jpg")
    if path.exists():
        try:
            return Image.open(path).convert("RGB"), "USGS"
        except Exception:
            path.unlink()
    for name, service, style in SOURCES[variant]:
        params={
            "bbox": ",".join(f"{n:.8f}" for n in extent),
            "bboxSR":"4326", "imageSR":"4326",
            "size":f"{size[0]},{size[1]}",
            "format":"jpg", "f":"image",
        }
        if style=="map":params["transparent"]="false"
        try:
            raw=request_bytes(service,params=params,tries=2)
            im=Image.open(io.BytesIO(raw)).convert("RGB")
            im.load()
            if im.size[0] < 300 or im.size[1] < 200:
                raise RuntimeError("Image too small")
            im.save(path,quality=83)
            return im,name
        except Exception as exc:
            print(f"Basemap fallback {name}: {exc}", flush=True)
    BASEMAP_FAILURES.append({"variant":variant,"extent":extent})
    return None,"UNAVAILABLE"

def paint_basemap(ax, extent, variant):
    im,source=basemap(extent,variant)
    if im is not None:
        ax.imshow(im, extent=extent, origin="upper", zorder=0, interpolation="bilinear", aspect="auto")
    else:
        ax.set_facecolor("#e9ecef")
        ax.text(0.5,0.5,"BASEMAP UNAVAILABLE",transform=ax.transAxes,ha="center",va="center",color="#a33",fontsize=14)
    ax.set_xlim(extent[0],extent[2])
    ax.set_ylim(extent[1],extent[3])
    return source

def outline(ax, geom, facecolor="none", edgecolor="#26364a", lw=2.0, alpha=1.0,zorder=3):
    if geom is None:return
    polys=list(geom.geoms) if geom.geom_type=="MultiPolygon" else [geom]
    for poly in polys:
        if poly.geom_type!="Polygon":continue
        xy=list(poly.exterior.coords)
        ax.add_patch(MplPolygon(xy,closed=True,facecolor=facecolor,edgecolor=edgecolor,linewidth=lw,alpha=alpha,zorder=zorder))
        for interior in poly.interiors:
            ax.add_patch(MplPolygon(list(interior.coords),closed=True,facecolor="none",edgecolor=edgecolor,linewidth=0.8,zorder=zorder))

def point_of(farm, geoms):
    key=(farm["county"],str(farm["farm_id"]))
    if geoms.get(key):
        p=unary_union(geoms[key]).representative_point()
        return (p.x,p.y),"verified_polygon"
    if farm.get("longitude") is not None and farm.get("latitude") is not None:
        return (float(farm["longitude"]),float(farm["latitude"])),"reported_point_unverified"
    return None,"no_coordinate"

def paint_point(ax, p, index, color, status, size=180):
    if p is None:return
    edge="white" if status=="verified_polygon" else color
    face=color if status=="verified_polygon" else "white"
    ax.scatter([p[0]],[p[1]],s=size,marker="o",facecolors=[face],edgecolors=[edge],linewidths=2,zorder=7)
    ax.text(p[0],p[1],str(index),color="white" if status=="verified_polygon" else "#20262c",fontsize=8,
            ha="center",va="center",fontweight="bold",zorder=8)

def styles():
    plt.rcParams.update({"font.family":"DejaVu Sans","pdf.fonttype":42,"savefig.facecolor":"white"})

def add_header(fig, county,variant,subtitle):
    fig.text(0.035,0.956,"SOUTH CAROLINA STATE UNIVERSITY  |  1890 AMP FARM ATLAS",fontsize=12,color="#31534a",weight="bold")
    fig.text(0.035,0.916,f"{county.upper()} COUNTY  |  {variant.upper()}",fontsize=22,color="#142d35",weight="bold")
    fig.text(0.035,0.882,subtitle,fontsize=10,color="#54656b")

def footer(fig,page,variant,source,unverified):
    msg=f"Page {page}   |   Background: {source}   |   Map generated {datetime.now(timezone.utc).strftime('%Y-%m-%d')} UTC"
    fig.text(0.035,0.037,msg,fontsize=8,color="#5b676d")
    if unverified:
        fig.text(0.98,0.037,"PROVISIONAL: some boundaries not georeferenced",fontsize=8,color="#ad5b24",ha="right",weight="bold")
    else:
        fig.text(0.98,0.037,"FSA program boundaries; not legal surveys",fontsize=8,color="#5b676d",ha="right")

def make_overview(pdf,county,variant,geom,farms,geoms,colors):
    fig=plt.figure(figsize=(17,11),facecolor="white")
    n=len(farms); verified=sum(bool(geoms.get((county,str(f["farm_id"])))) for f in farms)
    add_header(fig,county,variant,f"County distribution  |  {n} farm records  |  {verified} with extracted field geometry")
    ax=fig.add_axes([0.035,0.125,0.70,0.73])
    ext=adjusted_bounds(geom.bounds,min_width=0.1,min_height=0.1,padding=0.08)
    src=paint_basemap(ax,ext,variant)
    outline(ax,geom,edgecolor="#122f42",lw=2.5)
    for i,f in enumerate(farms):
        p,status=point_of(f,geoms)
        paint_point(ax,p,i+1,colors[i],status,180)
    ax.set_xticks([]);ax.set_yticks([])
    ax.set_title("County overview • numbered farm locations",loc="left",fontsize=12,pad=10)
    sidebar=fig.add_axes([0.77,0.125,0.20,0.72]);sidebar.axis("off")
    sidebar.text(0,0.99,"FARM INDEX",fontsize=15,fontweight="bold",va="top",color="#223c42")
    rows=max(len(farms),1);row_step=min(0.038,0.85/rows)
    for i,f in enumerate(farms):
        p,status=point_of(f,geoms)
        label=f"{i+1:02d}   Farm {f['farm_id']}"
        tail="polygon" if status=="verified_polygon" else ("point only" if p else "no location")
        y=0.94-i*row_step
        sidebar.plot([0.035],[y],marker="o",markersize=7,color=colors[i],transform=sidebar.transAxes)
        sidebar.text(0.09,y,label,fontsize=9,va="center",transform=sidebar.transAxes)
        sidebar.text(0.95,y,tail,fontsize=7,ha="right",va="center",color="#68747b",transform=sidebar.transAxes)
    sidebar.text(0,0.01,"Filled symbols = polygon location\nOutlined symbols = reported coordinate\nMaps should not be used as legal surveys",
                 va="bottom",fontsize=7.5,color="#657178",transform=sidebar.transAxes)
    footer(fig,1,variant,src,verified<len(farms))
    pdf.savefig(fig,dpi=210);plt.close(fig)
    return src

def make_details(pdf,county,variant,farms,geoms,colors):
    page=1
    for start in range(0,len(farms),2):
        subset=farms[start:start+2]
        fig=plt.figure(figsize=(17,11),facecolor="white")
        add_header(fig,county,variant,f"Farm detail panels  |  farms {start+1}-{start+len(subset)} of {len(farms)}")
        sources=set();unverified=False
        for col,f in enumerate(subset):
            idx=start+col;key=(county,str(f["farm_id"]))
            g=unary_union(geoms[key]) if geoms.get(key) else None
            p,status=point_of(f,geoms)
            if g:ext=adjusted_bounds(g.bounds,min_width=0.012,min_height=0.012,padding=0.23)
            elif p:ext=adjusted_bounds((p[0],p[1],p[0],p[1]),min_width=0.022,min_height=0.018,padding=0)
            else:ext=None
            box=[0.035+col*0.49,0.24,0.45,0.61]
            ax=fig.add_axes(box)
            if ext:
                src=paint_basemap(ax,ext,variant);sources.add(src)
                if g:
                    outline(ax,g,facecolor=colors[idx],edgecolor="#17191f",lw=2.4,alpha=0.44)
                    outline(ax,g,edgecolor=colors[idx],lw=2.8)
                elif p:
                    paint_point(ax,p,idx+1,colors[idx],status,250)
                    unverified=True
            else:
                ax.set_facecolor("#f0f1f2")
                ax.text(0.5,0.5,"No reliable location in supplied records",ha="center",va="center",transform=ax.transAxes,wrap=True)
                unverified=True
            ax.set_xticks([]);ax.set_yticks([])
            ax.set_title(f"{idx+1:02d}  |  FARM {f['farm_id']}",loc="left",fontsize=15,pad=10,fontweight="bold")
            fig.text(box[0],0.198,f"Tracts: {', '.join(f['tract_ids']) or 'Unspecified'}  |  Fields: {', '.join(f['field_ids']) or 'Unspecified'}",
                     fontsize=9,color="#344d55")
            if g:
                msg="Field polygon(s) extracted from geospatial FSA PDF; area checked against printed source."
            else:
                msg="Boundary NOT georeferenced. Marker is source-reported location only; no polygon is implied."
            fig.text(box[0],0.169,msg,fontsize=8.3,color="#2d674e" if g else "#a75524",wrap=True)
        page+=1
        footer(fig,page,variant,", ".join(sorted(sources)) if sources else "No basemap",unverified)
        pdf.savefig(fig,dpi=210);plt.close(fig)
    return page

def main():
    styles()
    counties=load_counties()
    inventory, geoms=load_data()
    links=load_source_map_links()
    bycounty=defaultdict(list)
    for f in inventory:bycounty[f["county"]].append(f)
    rows=[]
    for county,farms in sorted(bycounty.items()):
        if county not in counties:
            raise ValueError(f"No authoritative county geometry: {county}")
        farms=sorted(farms,key=lambda f:int(f["farm_id"]) if str(f["farm_id"]).isdigit() else f["farm_id"])
        colors=[COLORS(i%20) for i in range(len(farms))]
        for variant in ("Satellite","Topography"):
            filename=PDFDIR/(county.replace(" ","_")+f"_County_{variant}.pdf")
            with PdfPages(filename) as pdf:
                src=make_overview(pdf,county,variant,counties[county],farms,geoms,colors)
                total_pages=make_details(pdf,county,variant,farms,geoms,colors)
                src_pages=make_source_map_appendices(pdf,county,variant,farms,geoms,links,total_pages)
                total_pages+=src_pages
            count=sum(bool(geoms.get((county,str(f["farm_id"])))) for f in farms)
            row={"county":county,"variant":variant,"pdf":filename.name,"pdf_pages":total_pages,
                 "farm_count":len(farms),"farms_with_verified_fields":count,
                 "farms_without_verified_fields":len(farms)-count,
                 "original_fsa_map_reference_pages":src_pages,
                 "source_overview":src,"file_size_bytes":filename.stat().st_size}
            rows.append(row);ALL_LOGS.append(row)
            print(f"CREATED {filename.name}  pages={total_pages}  farms={len(farms)} verified_farms={count}",flush=True)
    with (QA/"county_atlas_status.csv").open("w",newline="") as fp:
        wr=csv.DictWriter(fp,fieldnames=rows[0].keys());wr.writeheader();wr.writerows(rows)
    with (QA/"basemap_failures.json").open("w") as fp:
        json.dump(BASEMAP_FAILURES,fp,indent=2)
    bundle=OUT/"SC_AMP_County_Atlas_PDFs.zip"
    with zipfile.ZipFile(bundle,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(PDFDIR.glob("*.pdf")):z.write(p,arcname="county_pdfs/"+p.name)
        for p in sorted(QA.glob("*")):z.write(p,arcname="qa/"+p.name)
    print(json.dumps({"summary":{"pdf_count":len(rows),"county_count":len(bycounty),"zip_bytes":bundle.stat().st_size,
         "basemap_failure_count":len(BASEMAP_FAILURES),"pdfs":[r["pdf"] for r in rows]}}),flush=True)

if __name__=="__main__":
    main()
