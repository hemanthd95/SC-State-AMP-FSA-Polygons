#!/usr/bin/env python3
"""Register the FSA Farm1662 field 1 against public NAIP aerial imagery.
Never publish a longitude/latitude field without passing image-matching QA.
The 2023 source image is a raster FSA map, not a GeoPDF.
"""
from pathlib import Path
import json, math, os, re, io, hashlib
import numpy as np
import cv2, fitz, requests
from PIL import Image
from shapely.geometry import Polygon, shape, mapping
from shapely.ops import transform
from pyproj import Geod, Transformer

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP/Derick Muhammed_FSA Map.pdf"
OUT=ROOT/"analysis/jasper_farm1662"
OUT.mkdir(parents=True,exist_ok=True)
GEOD=Geod(ellps="WGS84")
FIELD=np.float32([[1365,1599],[1699,1813],[927,3018],[585,3019],[573,2722]])
FSA_ACRES=5.01
PARCEL_PIN="039-00 -03-016"
FARM="1662"
URL_NAIP="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
URL_ESRI="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export"
S=requests.Session()
S.headers.update({"User-Agent":"SCSU-AMP-FSA-Aerial-Registration/2026 research geometry QA"})
R=6378137.0
SIDE=1024
SPAN=1000.0
STRIDE=600.0

def save_json(name,document):
    (OUT/name).write_text(json.dumps(document,indent=2,default=str)+"\n")

def get_json(url,params,timeout=25):
    r=S.get(url,params=params,timeout=timeout)
    r.raise_for_status()
    return r.json()

def meters(lon,lat):
    return R*math.radians(lon),R*math.log(math.tan(math.pi/4+math.radians(lat)/2))

def from_meters(x,y):
    return math.degrees(x/R), math.degrees(2*math.atan(math.exp(y/R))-math.pi/2)

def find_parcel():
    base="https://services3.arcgis.com/oJaBluQKw5aLHpzj/ArcGIS/rest/services/County_Parcels/FeatureServer/0/query"
    variants=["TaxPIN LIKE '%03-016%'","TaxPIN LIKE '%039-00%'"]
    out=[]
    for where in variants:
        try:
            d=get_json(base,dict(where=where,outFields="TaxPIN,GISAC,DeedAc",returnGeometry="true",outSR="4326",f="geojson"),40)
            for ft in d.get("features",[]):
                pin=str(ft.get("properties",{}).get("TaxPIN",""))
                norm=re.sub(r"[^0-9]","",pin)
                if norm.endswith("0390003016") or norm=="0390003016":
                    g=shape(ft["geometry"])
                    if g.is_valid and not g.is_empty:
                        ft["properties"]["match_evidence"]="parcel_number_from_public_address_directory_NOT_FSA_FARM_CONFIRMATION"
                        out.append((ft,g))
            if out:break
        except Exception as ex:
            print("PARCEL_LOOKUP_ERROR",where,str(ex)[:150],flush=True)
    if out:
        save_json("independent_public_parcel_candidates.geojson",{"type":"FeatureCollection","features":[x[0] for x in out]})
        return out[0][1]
    return None

def geocode():
    address="1066 Levy Rd, Hardeeville, SC 29927"
    hints=[]
    try:
        d=get_json("https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
            dict(address=address,benchmark="Public_AR_Current",vintage="Current_Current",format="json"),35)
        for match in d.get("result",{}).get("addressMatches",[]):
            p=match["coordinates"]
            hints.append(("census_address",float(p["x"]),float(p["y"])))
    except Exception as ex:print("CENSUS_GEOCODE_ERROR",str(ex)[:150],flush=True)
    try:
        d=get_json("https://nominatim.openstreetmap.org/search",
            dict(q=address,format="json",limit=2),35)
        for row in d:
            hints.append(("osm_address",float(row["lon"]),float(row["lat"])))
    except Exception as ex:print("OSM_GEOCODE_ERROR",str(ex)[:150],flush=True)
    return hints

def source_image():
    if not SRC.is_file():raise FileNotFoundError(SRC)
    content=SRC.read_bytes()
    if content[:40].startswith(b"version https://git-lfs.github.com"):
        raise RuntimeError("Git LFS source is a pointer; checkout must use lfs:true")
    doc=fitz.open(stream=content,filetype="pdf")
    pix=doc[0].get_pixmap(matrix=fitz.Matrix(2,2),colorspace=fitz.csRGB,alpha=False)
    im=cv2.imdecode(np.frombuffer(pix.tobytes("png"),dtype=np.uint8),cv2.IMREAD_COLOR)
    if im.shape[:2] != (4992,2304):
        raise RuntimeError("Original page coordinate calibration changed: "+str(im.shape))
    doc.close()
    # FSA displayed satellite window; exclude page headings/legend/black margins.
    x0,y0,x1,y1=(48,1215,2220,3380)
    sub=im[y0:y1,x0:x1]
    factor=1120/max(sub.shape[:2])
    new=cv2.resize(sub,None,fx=factor,fy=factor,interpolation=cv2.INTER_AREA)
    pts=(FIELD-np.array([x0,y0],np.float32))*factor
    cv2.imwrite(str(OUT/"original_fsa_crop.png"),new)
    return new,pts,{"source_sha256":hashlib.sha256(content).hexdigest(),
                      "map_crop_original_xyxy":[x0,y0,x1,y1],
                      "source_render_shape_wh":[2304,4992],"crop_scale":float(factor)}

def prepare(image):
    return cv2.createCLAHE(clipLimit=2,tileGridSize=(8,8)).apply(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY))

SIFT=cv2.SIFT_create(nfeatures=3500,contrastThreshold=0.008,edgeThreshold=18)
def test_match(src,src_keys,src_desc,tile):
    keys,desc=SIFT.detectAndCompute(prepare(tile),None)
    if desc is None or len(keys)<60:return None
    pairs=cv2.FlannBasedMatcher(dict(algorithm=1,trees=6),dict(checks=70)).knnMatch(src_desc,desc,k=2)
    good=[a for pair in pairs if len(pair)==2 for a,b in [pair] if a.distance<.73*b.distance]
    if len(good)<32:return None
    p=np.float32([src_keys[m.queryIdx].pt for m in good])
    q=np.float32([keys[m.trainIdx].pt for m in good])
    H,mask=cv2.findHomography(p,q,cv2.USAC_MAGSAC,4,maxIters=5000,confidence=.999)
    if H is None or mask is None:return None
    keep=mask.ravel().astype(bool)
    n=int(keep.sum())
    if n<30:return None
    proj=cv2.perspectiveTransform(p[:,None,:],H)[:,0,:]
    rmse=float(np.sqrt(np.mean(np.sum((proj[keep]-q[keep])**2,axis=1))))
    srcspread=np.ptp(p[keep],axis=0)
    dstspread=np.ptp(q[keep],axis=0)
    if rmse>3 or min(srcspread)<130 or min(dstspread)<95:return None
    test_quad=np.float32([[[100,100],[900,100],[900,900],[100,900]]])
    projected=cv2.perspectiveTransform(test_quad,H)[0]
    area=abs(cv2.contourArea(projected))
    if area<3000 or area>3000000:return None
    return dict(H=H,n=n,rmse=rmse,srcspread=srcspread.tolist(),dstspread=dstspread.tolist(),
                score=n*(1+min(srcspread)/500),good_matches=len(good))

def query_image(x,y,kind):
    bbox=(x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2)
    url=URL_NAIP if kind=="USGS_NAIP" else URL_ESRI
    try:
        r=S.get(url,params=dict(bbox=",".join(f"{v:.2f}" for v in bbox),
                 bboxSR=3857,imageSR=3857,size=f"{SIDE},{SIDE}",format="jpg",f="image"),timeout=14)
        r.raise_for_status()
        tile=cv2.imdecode(np.frombuffer(r.content,np.uint8),cv2.IMREAD_COLOR)
        return tile,bbox if tile is not None and tile.shape[:2]==(SIDE,SIDE) else (None,None)
    except Exception:return None,None

def candidate_from_match(reg,pts,bbox):
    predicted=cv2.perspectiveTransform(pts[None,:,:],reg["H"])[0]
    x0,y0,x1,y1=bbox
    coords=[from_meters(x0+float(px)/SIDE*(x1-x0),y1-float(py)/SIDE*(y1-y0)) for px,py in predicted]
    coords.append(coords[0])
    poly=Polygon(coords)
    if not poly.is_valid or poly.is_empty:return None
    area=abs(GEOD.geometry_area_perimeter(poly)[0])/4046.8564224
    if not 0.7*FSA_ACRES<=area<=1.30*FSA_ACRES:return None
    return poly,predicted,float(area)

def run():
    img,pts,source=source_image()
    keys,desc=SIFT.detectAndCompute(prepare(img),None)
    if desc is None:raise RuntimeError("No aerial features in FSA source")
    parcel=find_parcel()
    hints=geocode()
    if parcel is not None:
        cent=parcel.centroid
        hints.insert(0,("jasper_parcel_lookup_not_fsa_proof",cent.x,cent.y))
    all_hints=[dict(method=a,longitude=b,latitude=c) for a,b,c in hints]
    print("LOCATION_HINTS",all_hints,flush=True)
    best=None
    ntiles=0
    # Download many independent georeferenced tiles concurrently so a slow
    # public image endpoint cannot hold an entire farm search hostage.
    from concurrent.futures import ThreadPoolExecutor, as_completed
    tile_jobs=[]
    for method,lon,lat in hints:
        if not (-82<lon<-80 and 31.5<lat<33.5):continue
        base_x,base_y=meters(lon,lat)
        for kind in ["USGS_NAIP","Esri_World_Imagery"]:
            for dx in range(-3,4):
                for dy in range(-3,4):
                    tile_jobs.append((method,kind,dx,dy,base_x+dx*STRIDE,base_y+dy*STRIDE))
    def load_one(job):
        return job,query_image(job[4],job[5],job[1])
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures=[pool.submit(load_one,job) for job in tile_jobs]
        for future in as_completed(futures):
            try:
                job,result=future.result()
                tile,bbox=result
            except Exception as exc:
                print("TILE_ERROR",str(exc)[:100],flush=True)
                continue
            method,kind,dx,dy,_,_=job
            ntiles+=1
            if tile is None or not isinstance(bbox,(tuple,list)) or len(bbox)!=4:continue
            reg=test_match(img,keys,desc,tile)
            if reg is None:continue
            result=candidate_from_match(reg,pts,bbox)
            if result is None:continue
            poly,pred,acres=result
            overlap=None
            if parcel is not None:
                overlap=float(poly.intersection(parcel).area/poly.area) if poly.area else 0.
            score=reg["score"]*(1+max(0,overlap or 0))
            if best is None or score>best["score"]:
                best=dict(poly=poly,pred=pred,acres=acres,reg=reg,kind=kind,
                    method=method,bbox=bbox,tile=tile,
                    dx=dx,dy=dy,score=score,parcel_overlap=overlap)
                print("BEST",method,kind,dx,dy,"inliers",reg["n"],"rmse",round(reg["rmse"],2),"acres",round(acres,2),"parcel_overlap",overlap,flush=True)
                if reg["n"]>=150 and reg["rmse"]<1.1 and abs(acres-FSA_ACRES)<.15 and (overlap is None or overlap>.75):
                    print("STRONG_MATCH_STOPPING_EARLY",flush=True)
                    for f in futures:f.cancel()
                    break
    report=dict(farm_id=FARM,tract_id="2387",field_id="1",producer="Derick Muhammed",
         fsa_source_acres=FSA_ACRES,enrollment_total_field_acres=5.91,
         work_source=source,location_hints=all_hints,tiles_attempted=ntiles,
         exact_fsa_field_footprint_gps_used=False,
         warning="Source map fields not land surveys; position accepted only with image registration")
    if best is None:
        report["status"]="NO_GEOREFERENCED_FIELD_ACCEPTED_NO_NAIP_MATCH_PASSED_QA"
        save_json("jasper_farm1662_naip_qa.json",report)
        print("NO_ACCEPTABLE_MATCH",flush=True)
        return
    b=best
    passed=(b["reg"]["n"]>=45 and b["reg"]["rmse"]<=2.5 and
       min(b["reg"]["srcspread"])>=150 and min(b["reg"]["dstspread"])>=110)
    report.update(status="NAIP_SIFT_GEOMETRIC_MATCH_REQUIRES_VISUAL_FIELD_REVIEW" if passed else "CANDIDATE_ONLY_NOT_ACCEPTED",
       source_imagery=b["kind"],registration_hint=b["method"],homography=b["reg"]["H"].tolist(),
       matched_inliers=b["reg"]["n"],matched_good_pairs=b["reg"]["good_matches"],
       inlier_rmse_px=b["reg"]["rmse"],source_inlier_spread_px=b["reg"]["srcspread"],
       satellite_inlier_spread_px=b["reg"]["dstspread"],
       parcel_overlap_fraction=b["parcel_overlap"],bbox_epsg3857=b["bbox"],
       polygon_calculated_acres=b["acres"],source_acreage_difference_percent=100*(b["acres"]/FSA_ACRES-1),
       polygon_coordinates_wgs84=list(b["poly"].exterior.coords),
       automated_georegistration_qa_passed=bool(passed))
    overlay=b["tile"].copy()
    ptsint=np.round(b["pred"]).astype(np.int32)
    cv2.polylines(overlay,[ptsint],True,(15,20,255),3,cv2.LINE_AA)
    cv2.imwrite(str(OUT/"farm1662_source_outline_on_naip.jpg"),overlay)
    save_json("jasper_farm1662_naip_qa.json",report)
    if passed:
        feature={"type":"Feature","properties":{"producer":"Derick Muhammed","farm_id":FARM,
            "tract_id":"2387","field_id":"1","fsa_acres":FSA_ACRES,
            "geodetic_acres":round(b["acres"],3),
            "source_pdf":"Derick Muhammed_FSA Map.pdf","source_imagery":b["kind"],
            "image_registration_inliers":b["reg"]["n"],
            "image_registration_rmse_px":round(b["reg"]["rmse"],3),
            "registration_method":"SIFT-USAC homography to geographically referenced aerial imagery",
            "geometry_status":"AERIAL_REGISTERED_APPROXIMATE_REQUIRES_INDEPENDENT_VISUAL_REVIEW_NOT_SURVEY",
            "address_role":"geographic_search_hint_only","qa_report":"analysis/jasper_farm1662/jasper_farm1662_naip_qa.json"},
          "geometry":mapping(b["poly"])}
        path=ROOT/"geojson/counties/jasper_farm1662_derick_muhammed_candidate.geojson"
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({"type":"FeatureCollection","features":[feature]},indent=2)+"\n")
        print("GEOJSON_CANDIDATE_WRITTEN",path,flush=True)

if __name__=="__main__":
    try:run()
    except Exception as exc:
        save_json("jasper_farm1662_naip_qa.json",{"status":"EXECUTION_ERROR","message":str(exc)})
        raise
