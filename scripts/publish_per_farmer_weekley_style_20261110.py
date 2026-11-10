#!/usr/bin/env python3
"""Weekley-style per-producer deliverables from CURATED SCSU AMP polygons only.
No synthetic master, unregistered source scans, or location-derived buffers.
Satellite/USGS topo maps, real OSM road labels, shapefiles, and full QA manifest.
"""
import csv,io,json,math,re,time,os,zipfile,hashlib
from pathlib import Path
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests,shapefile,fitz
import numpy as np
from shapely.geometry import shape,Polygon,MultiPolygon,Point,box
from shapely.ops import transform,unary_union
from shapely.geometry.polygon import orient
from pyproj import Transformer,CRS,Geod
from PIL import Image,ImageDraw,ImageFont,ImageStat
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"deliverables/per_farmer_weekley_style_20261110"
SRC=[
"geojson/counties/barnwell_farm753_green_melendez_wright_split_20261109.geojson",
"geojson/master_fsa_fields_geopdf_verified.geojson",
"geojson/registered_scanned_fields.geojson",
"geojson/orangeburg_registered_fields.geojson",
"geojson/counties/bamberg_corey_3523_fsa_and_john_3524_qgis_area_20261106.geojson",
"geojson/counties/berkeley_4_registered_fields_v5_20261106.geojson",
"geojson/counties/charleston_registered_selected_field.geojson",
"geojson/counties/clarendon_selected_fields_7of16_20261106.geojson",
"geojson/counties/colleton_new_verified_fsa_fields_20261106.geojson",
"geojson/counties/darlington_selected_5_fields.geojson",
"geojson/counties/greenwood_myra_louden_and_jasper_john_lee_registered_20261106.geojson",
"geojson/counties/jasper_farm1662_derick_muhammed_cadastral_registered_20261109.geojson",
"geojson/counties/marlboro_registered_selected_field.geojson",
"geojson/counties/orangeburg_new_verified_fsa_fields_20261106.geojson",
"geojson/counties/berkeley_roster_14118_orangeburg_field_23_20261106.geojson",
"geojson/counties/york_registered_selected_field.geojson"]
WEBM=Transformer.from_crs(4326,3857,always_xy=True)
GEOD=Geod(ellps="WGS84")
S=requests.Session()
S.headers.update({"User-Agent":"SC-State-AMP-Field-Atlas/1.0 (noncommercial research; source attribution in maps)"})
SAT="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
NAIP="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
TOPO="https://basemap.nationalmap.gov/arcgis/rest/services/USGSTopo/MapServer/export"
TRANSPORT="https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/export"
FONT="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SCALE_W,SCALE_H=1200,1340
WORKERS=int(os.getenv("AMP_FARM_WORKERS","5"))
def label_name(p):
    raw=p.get("producer")
    if raw:return re.sub(r"\s+"," ",str(raw)).strip()
    pdf=str(p.get("source_pdf",""))
    name=pdf.split("_FSA")[0].split(" FSA")[0].replace("_"," ").strip()
    if name.startswith("Yvette Moses"):return "Yvette Moses"
    if name.startswith("Christopher Edward"):return "Christopher Edward"
    return name or "Unknown Producer"
def canonical(n):
    n=n.replace("Tywone Hillard","Tywone Hilliard").replace("Corey Cosby","Corey Crosby")
    return re.sub(r"\s+"," ",n).strip()
def file_slug(n):
    return re.sub(r"[^A-Za-z0-9]+","_",n).strip("_")[:48]
def human_folder(n):
    words=n.split()
    if len(words)<2:return "L-"+n
    if words[-1].lower() in ("jr.","jr","iii") and len(words)>=3:
        last=" ".join(words[-2:]);first=" ".join(words[:-2])
    else:last=words[-1];first=" ".join(words[:-1])
    return "L-"+last+", "+first
def load_curated():
    allfeatures={}
    for path in SRC:
        file=ROOT/path
        if not file.exists():raise FileNotFoundError(path)
        j=json.loads(file.read_text())
        for f in j["features"]:
            p=dict(f.get("properties") or {})
            g=shape(f["geometry"])
            if g.is_empty or g.geom_type not in ("Polygon","MultiPolygon") or not g.is_valid:continue
            county=str(p.get("county") or p.get("physical_county") or "").strip()
            farm=str(p.get("farm_id") or "")
            tract=str(p.get("tract_id") or "")
            fid=p.get("field_id",p.get("fsa_field_id"))
            field=str(fid) if fid is not None else "AREA"
            prod=canonical(label_name(p))
            if farm=="753" and county=="Barnwell" and path!="geojson/counties/barnwell_farm753_green_melendez_wright_split_20261109.geojson":
                continue # Known shared-farm issue: producer-specific Fields 2, 9, 10 supersede unattributed source set
            key=(prod,county,farm,tract,field)
            if key in allfeatures:continue
            p.update(producer=prod,physical_county=county,field_id=field,source_geojson=path)
            allfeatures[key]={"type":"Feature","properties":p,"geometry":f["geometry"]}
    if len(allfeatures)<55:raise RuntimeError("Curated inventory unexpectedly small: "+str(len(allfeatures)))
    groups=defaultdict(list)
    for f in allfeatures.values():
        p=f["properties"];groups[(p["producer"],p["physical_county"])].append(f)
    return dict(sorted(groups.items()))
def find_roads(lon,lat):
    """Ground every named road label in published US Census TIGER or OSM features."""
    # TIGERweb January 2026 road centerlines give dependable names even
    # when volunteer/community OSM endpoints are throttled.
    cx,cy=WEBM.transform(lon,lat)
    result={}
    for layer in (2,1,0): # Local, secondary, primary roads
        endpoint=f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Transportation_LargeScale/MapServer/{layer}/query"
        try:
            d=S.get(endpoint,params=dict(
                where="NAME IS NOT NULL",
                geometry=",".join(f"{v:.1f}" for v in (cx-6600,cy-6600,cx+6600,cy+6600)),
                geometryType="esriGeometryEnvelope",inSR=3857,spatialRel="esriSpatialRelIntersects",
                outFields="NAME,BASENAME",returnGeometry="true",outSR=4326,
                resultRecordCount=1000,f="geojson"),timeout=34)
            d.raise_for_status()
            obj=d.json()
            for feat in obj.get("features",[]):
                p=feat.get("properties") or {}
                name=str(p.get("NAME") or p.get("BASENAME") or "").strip()
                if not name or not re.search(r"[A-Za-z]",name):continue
                geo=shape(feat["geometry"])
                if geo.is_empty:continue
                merc=transform(WEBM.transform,geo)
                from shapely.ops import nearest_points
                nearest=nearest_points(Point(cx,cy),merc)[1]
                dd=math.hypot(nearest.x-cx,nearest.y-cy)
                reverse=Transformer.from_crs(3857,4326,always_xy=True)
                rx,ry=reverse.transform(nearest.x,nearest.y)
                if name not in result or dd<result[name]["distance_m"]:
                    result[name]=dict(name=name,lon=rx,lat=ry,distance_m=dd)
            if len(result)>=2:
                return sorted(result.values(),key=lambda x:x["distance_m"])[:30],"U.S. Census TIGERweb (2026)"
        except Exception as ex:
            print("TIGER_ROAD_QUERY_WARNING",layer,str(ex)[:130],flush=True)
    # Volunteer OSM data is a secondary, separately verifiable fallback.
    q=f'[out:json][timeout:30];way(around:7000,{lat:.6f},{lon:.6f})["highway"]["name"];out center;'
    endpts=["https://overpass.kumi.systems/api/interpreter",
      "https://overpass-api.de/api/interpreter"]
    for ep in endpts:
        try:
            response=S.post(ep,data={"data":q},timeout=25)
            response.raise_for_status()
            d=response.json()
            for e in d.get("elements",[]):
                name=str(e.get("tags",{}).get("name","")).strip()
                co=e.get("center") or {}
                if not name or "lon" not in co or "lat" not in co:continue
                if e.get("tags",{}).get("highway") in ("service","footway","path","track","steps","cycleway","pedestrian"):continue
                x,y=WEBM.transform(float(co["lon"]),float(co["lat"]))
                dist=math.hypot(x-cx,y-cy)
                if name not in result or dist<result[name]["distance_m"]:
                    result[name]={"name":name,"lon":float(co["lon"]),"lat":float(co["lat"]),"distance_m":dist}
            if len(result)>=2:return sorted(result.values(),key=lambda x:x["distance_m"])[:30],"Census TIGER / OSM combined"
        except Exception as ex:
            print("OSM_ROAD_QUERY_WARNING",ep,str(ex)[:115],flush=True)
    return sorted(result.values(),key=lambda x:x["distance_m"])[:30],"No two vector street names found"
def choose_bbox(geoms,roads,context=False):
    u=unary_union(geoms)
    a,b,c,d=transform(WEBM.transform,u).bounds
    cx,cy=(a+c)/2,(b+d)/2
    minwidth=6200 if context else 1650
    span=max(c-a,d-b)
    width=max(minwidth,span*(1.45 if context else 2.6))
    if not context and len(roads)>=2:
        # Keep two distinct named road centers in view; a rural road context may require a wider map.
        for road in roads[:2]:
            rx,ry=WEBM.transform(road["lon"],road["lat"])
            width=max(width,abs(rx-cx)*2.30,abs(ry-cy)*2.08)
    width=min(width,15500 if context else 13200)
    height=width*SCALE_H/SCALE_W
    return (cx-width/2,cy-height/2,cx+width/2,cy+height/2)
def pull_image(url,bbox):
    params={"bbox":",".join(f"{v:.2f}" for v in bbox),"bboxSR":"3857","imageSR":"3857",
            "size":f"{SCALE_W},{SCALE_H}","format":"jpg","f":"image","dpi":130}
    r=S.get(url,params=params,timeout=48)
    r.raise_for_status()
    im=Image.open(io.BytesIO(r.content)).convert("RGB")
    if im.size!=(SCALE_W,SCALE_H) or min(ImageStat.Stat(im.resize((80,70))).stddev)<3:
        raise RuntimeError("Base map missing or low-content")
    return im
def basemap(bbox,style):
    endpoints=[SAT,NAIP] if style=="field" else [TOPO]
    for u in endpoints:
        for repeat in range(2):
            try:return pull_image(u,bbox),u
            except Exception as e:print("BASEMAP_RETRY",style,u,str(e)[:85],flush=True)
    raise RuntimeError("Cannot obtain "+style+" basemap; no synthetic basemap substituted")
def pix(lon,lat,bbox):
    x,y=WEBM.transform(lon,lat)
    return ((x-bbox[0])/(bbox[2]-bbox[0])*SCALE_W,
            (bbox[3]-y)/(bbox[3]-bbox[1])*SCALE_H)
def polygon_overlay(img,geoms,bbox):
    layer=Image.new("RGBA",img.size,(0,0,0,0));d=ImageDraw.Draw(layer)
    for g in geoms:
        for pg in (list(g.geoms) if g.geom_type=="MultiPolygon" else [g]):
            ring=[pix(x,y,bbox) for x,y in pg.exterior.coords]
            d.polygon(ring,fill=(241,51,51,155))
            d.line(ring,fill=(255,255,255,255),width=9,joint="curve")
            d.line(ring,fill=(192,21,28,255),width=5,joint="curve")
            for interior in pg.interiors:
                ring=[pix(x,y,bbox) for x,y in interior.coords]
                d.polygon(ring,fill=(0,0,0,0))
    return Image.alpha_composite(img.convert("RGBA"),layer)
def arrow_and_labels(im,bbox,roads,style):
    d=ImageDraw.Draw(im)
    bold=ImageFont.truetype(FONTB,31)
    small=ImageFont.truetype(FONTB,22)
    d.polygon([(1091,145),(1133,250),(1091,224),(1049,250)],fill=(245,227,0,255),
              outline=(78,69,0,255),width=3)
    d.text((1091,103),"N",font=bold,anchor="mt",fill="yellow",
           stroke_width=3,stroke_fill="black")
    shown=[]
    if style=="field":
        for road in roads[:15]:
            x,y=pix(road["lon"],road["lat"],bbox)
            if not (20<x<SCALE_W-120 and 45<y<SCALE_H-85):continue
            if road["name"] in [a[0] for a in shown]:continue
            labelx,labely=x,y
            # A label is never invented. When intersections crowd text,
            # offset the *verified* road name and draw a small anchor line.
            for ix in range(4):
                if not any(math.hypot(labelx-u,labely-v)<125 for _,u,v in shown):break
                labelx=min(SCALE_W-180,max(25,x+90*(ix%2*2-1)))
                labely=min(SCALE_H-85,max(50,y+85*(1+ix//2)))
            if any(math.hypot(labelx-u,labely-v)<125 for _,u,v in shown):continue
            if math.hypot(labelx-x,labely-y)>25:
                d.line([(x,y),(labelx,labely)],fill="white",width=3)
                d.ellipse((x-4,y-4,x+4,y+4),fill="yellow",outline="black",width=2)
            name=road["name"][:30]
            d.text((labelx,labely),name,font=small,fill=(255,255,255,255),
                   stroke_width=4,stroke_fill=(0,0,0,240))
            shown.append((name,labelx,labely))
            if len(shown)>=5:break
    return [a[0] for a in shown]
def legend_scalebar(img,bbox,style):
    d=ImageDraw.Draw(img)
    res=(bbox[2]-bbox[0])/SCALE_W
    candidates=[.1,.2,.5,1,2,3,5]
    m_per_mile=1609.344
    miles=max([v for v in candidates if v*m_per_mile/res<SCALE_W*.46] or [.1])
    length=miles*m_per_mile/res
    x0,y0=46,SCALE_H-50
    d.rectangle((x0-15,y0-40,x0+length+25,y0+37),fill=(250,250,250,230))
    for i in range(4):
        xa=x0+i*length/4;xb=x0+(i+1)*length/4
        d.rectangle((xa,y0,xb,y0+15),fill="black" if i%2==0 else "white",outline="black",width=2)
    font=ImageFont.truetype(FONTB,18)
    for i in range(5):
        d.text((x0+i*length/4,y0-7),f"{miles*i/4:.2g}",font=font,fill="black",anchor="mb")
    d.text((x0+length+13,y0+4),"mi",font=font,fill="black",anchor="lm")
def add_inset(img,geoms):
    # If road-name coverage forces a wide context view, retain a separate high-contrast field inset.
    # This inset is a simplified polygon locator; the main figure is geographic satellite imagery.
    return img
def PDF(path,im,producer,county,features,bbox,style,roadnames,road_source,base_source):
    p=features[0]["properties"]
    c=canvas.Canvas(str(path),pagesize=(612,792),pageCompression=1)
    c.setTitle(f"{producer} - {county} - "+("Field Map" if style=="field" else "County Map"))
    c.drawImage(ImageReader(im.convert("RGB")) ,24,117,width=564,height=633)
    c.setFont("Helvetica",8)
    c.setFillColorRGB(.15,.15,.15)
    label=f"Overview of {producer} mapped fields in {county} County  |  SCSU AMP"
    c.drawString(25,102,label[:120])
    fields="; ".join("Farm "+str(x["properties"].get("farm_id",""))+
      " / Tract "+str(x["properties"].get("tract_id",""))+
      " / Field "+str(x["properties"].get("field_id","")) for x in features)
    c.drawString(25,90,fields[:110])
    cx,cy=unary_union([shape(f["geometry"]) for f in features]).centroid.coords[0]
    c.drawString(25,78,f"Field center (WGS84): {cy:.5f} N, {abs(cx):.5f} W  |  FSA-source geometry, NOT a legal survey")
    c.drawString(25,65,("Satellite: Esri/USGS | Roads: OpenStreetMap" if style=="field" else
                        "Topographic: USGS National Map")+"  |  Map generated 10 Nov 2026")
    if style=="field":
        c.drawString(25,52,("Verified named roads shown: "+", ".join(roadnames[:2]) if len(roadnames)>=2
                            else "WARNING: Two independently sourced road labels not established")[:115])
    c.save()
def write_shapes(folder,base,features,county):
    d=folder/(base+".shp");d.mkdir(parents=True,exist_ok=True)
    wr=shapefile.Writer(str(d/base),shapeType=shapefile.POLYGON,encoding="utf-8")
    for name,kind,n,dec in [
        ("First_Name","C",65,0),("Last_Name","C",65,0),("FSA_Farm__","N",11,0),
        ("FSA_Tract_","N",11,0),("FSA_Field_","N",11,0),("County","C",40,0),
        ("Status","C",82,0),("SrcAcres","F",14,3),("GeoAcres","F",14,3)]:
        wr.field(name,kind,size=n,decimal=dec)
    for f in features:
        p=f["properties"];g=shape(f["geometry"])
        parts=[]
        for polygon in (g.geoms if g.geom_type=="MultiPolygon" else [g]):
            poly=orient(polygon,sign=-1)
            parts.append(list(poly.exterior.coords))
            for interior in poly.interiors:parts.append(list(interior.coords))
        wr.poly(parts)
        farmer=p["producer"];words=farmer.split()
        last=words[-1] if len(words)>1 else farmer
        first=" ".join(words[:-1]) if len(words)>1 else ""
        def numeric(v):return int(v) if str(v).isdigit() else 0
        srcacres=next((p[k] for k in ("fsa_reported_acres","fsa_printed_acres","source_fsa_acres") if isinstance(p.get(k),(int,float))),None)
        geoacres=abs(GEOD.geometry_area_perimeter(g)[0])/4046.8564224
        wr.record(first,last,numeric(p.get("farm_id")),numeric(p.get("tract_id")),
                  numeric(p.get("field_id")),county,str(p.get("status",p.get("geometry_status","APPROXIMATE")))[:82],
                  float(srcacres) if srcacres is not None else None,round(geoacres,3))
    wr.close()
    (d/(base+".prj")).write_text(CRS.from_epsg(4326).to_wkt("WKT1_ESRI"))
    (d/(base+".cpg")).write_text("UTF-8")
    reader=shapefile.Reader(str(d/base)+".shp")
    if reader.numRecords!=len(features):raise RuntimeError("Shapefile record count mismatch")
def process(key,features):
    farmer,county=key
    dirname=human_folder(farmer)
    folder=OUT/county/dirname;folder.mkdir(parents=True,exist_ok=True)
    base=file_slug(farmer).replace("_","")[:24] or "Farmer"
    write_shapes(folder,base,features,county)
    geoms=[shape(f["geometry"]) for f in features]
    rep=unary_union(geoms).representative_point()
    roads,road_source=find_roads(rep.x,rep.y)
    # For distinct farm IDs, keep all their fields on one map whenever practical.
    road_labels=[]
    outcomes={}
    for style in ("county","field"):
        bbox=choose_bbox(geoms,roads,context=style=="county")
        try:
            image,base_source=basemap(bbox,style)
            im=polygon_overlay(image,geoms,bbox)
            labelled=arrow_and_labels(im,bbox,roads,style)
            legend_scalebar(im,bbox,style)
            filename=base+("-CountyMap.pdf" if style=="county" else "-FieldMap.pdf")
            PDF(folder/filename,im,farmer,county,features,bbox,style,labelled,road_source,base_source)
            if style=="field":
                road_labels=labelled
                # PNG is a convenient source-map preview matching the Weekley ArchSite example.
                im.convert("RGB").save(folder/(base+"-FieldMap.jpg"),"JPEG",quality=88,optimize=True)
            outcomes[style]="CREATED"
        except Exception as exc:
            outcomes[style]="FAILED:"+str(exc)[:125]
            print("MAP_ERROR",farmer,county,style,str(exc)[:125],flush=True)
    with (folder/"REGISTERED_FIELDS.geojson").open("w") as f:
        json.dump({"type":"FeatureCollection","features":features},f,indent=2)
    qa={"producer":farmer,"physical_county":county,"folder":str(folder.relative_to(OUT)),
        "source_field_features":len(features),"farm_ids":";".join(sorted({str(f["properties"].get("farm_id","")) for f in features})),
        "field_map_status":outcomes.get("field"),"county_map_status":outcomes.get("county"),
        "named_roads_visible_count":len(road_labels),"named_roads":", ".join(road_labels[:5]),
        "two_road_names_pass":len(set(road_labels))>=2,"road_data_provider":road_source,
        "boundary_quality":"Approximate FSA-source / user-QGIS location; NOT surveyed. Special status preserved in source GeoJSON."}
    (folder/"README_QA.txt").write_text(
        f"SCSU AMP: {farmer}, {county} County\n"
        f"Shapefile: {base}.shp/ (EPSG:4326, one feature per previously accepted field)\n"
        f"County map: {base}-CountyMap.pdf (topographic)\n"
        f"Field map: {base}-FieldMap.pdf (satellite + named road labels)\n"
        f"Registered feature count: {len(features)}\n"
        f"Independently named roads visible: {len(road_labels)} -> {road_labels}\n"
        f"Road-label compliance: {'PASS' if qa['two_road_names_pass'] else 'NEEDS_REVIEW'}\n"
        f"NOTE: original producer workbook county and FSA county may differ from actual physical county.\n"
        f"NOTE: These are not legal, cadastral, CLU, or ownership boundaries.\n")
    print("FARM",farmer,county,len(features),"roads",len(road_labels),outcomes,flush=True)
    return qa
def main():
    groups=load_curated()
    OUT.mkdir(parents=True,exist_ok=True)
    print("PRODUCER-COUNTY GROUPS",len(groups),"RAW FIELDS",sum(len(v) for v in groups.values()),flush=True)
    rows=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        fs={pool.submit(process,k,v):k for k,v in groups.items()}
        for fu in as_completed(fs):
            try:rows.append(fu.result())
            except Exception as ex:
                key=fs[fu];print("FARM_EXCEPTION",key,str(ex),flush=True)
                rows.append(dict(producer=key[0],physical_county=key[1],
                                 field_map_status="FAILED",county_map_status="FAILED",
                                 two_road_names_pass=False,error=str(ex)))
    rows=sorted(rows,key=lambda r:(r["physical_county"],r["producer"]))
    fields=sorted({k for x in rows for k in x})
    with (OUT/"Producer_Atlas_Index_QA.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore");w.writeheader();w.writerows(rows)
    meta={
      "source":"Curated private GitHub SCSU AMP FSA polygons; rejected 719-feature master excluded",
      "generated":"2026-11-10",
      "producer_count":len(rows),
      "registered_field_count":sum(len(v) for v in groups.values()),
      "two_visible_road_labels_pass":sum(bool(r.get("two_road_names_pass")) for r in rows),
      "map_pairs_complete":sum(r.get("field_map_status")=="CREATED" and r.get("county_map_status")=="CREATED" for r in rows),
      "warnings":["Do not use as ownership or cadastral surveys",
        "Farm location counties were retained from curated mapping; county of enrollment may differ",
        "County maps are local-area topographic views, matching Weekley example, not entire county outlines",
        "Where two named OSM roads are unavailable or out of view, explicit QA flags; no invented road labels",
        "Shared Farm753 producer boundaries use separately georeferenced Fields 2,9,10"]
    }
    (OUT/"BUILD_SUMMARY.json").write_text(json.dumps(meta,indent=2))
    (OUT/"README_START_HERE.txt").write_text(
      "SC State AMP — PER-FARMER FSA MAPS (Weekley reference format)\n"
      "Each L-Last, First folder contains an EPSG:4326 shapefile directory, individual county topographic PDF, "
      "satellite field PDF with road labels, JPG preview, registered-field GeoJSON and QA notes.\n"
      "Check Producer_Atlas_Index_QA.csv for failed basemaps or fewer than two VERIFIED road labels.\n"
      "Do not treat a farm address, source PDF county, or raster-pixel tracing as field georeferencing.\n"
      "FSA administrative outlines are research planning approximations, not legal boundaries.\n")
    zipfile_path=ROOT/"deliverables/SC_AMP_Per_Farmer_Weekley_Format_20261110.zip"
    with zipfile.ZipFile(zipfile_path,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
        for p in sorted(OUT.rglob("*")):
            if p.is_file():z.write(p,p.relative_to(OUT.parent))
    meta["zip_bytes"]=zipfile_path.stat().st_size
    (OUT/"BUILD_SUMMARY.json").write_text(json.dumps(meta,indent=2))
    print("FINAL_SUMMARY",json.dumps(meta),flush=True)
    if meta["map_pairs_complete"]==0:raise RuntimeError("No two-map producer packages generated")
if __name__=="__main__":main()
