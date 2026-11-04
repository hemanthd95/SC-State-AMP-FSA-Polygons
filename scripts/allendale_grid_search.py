#!/usr/bin/env python3
"""Search geographic image tiles for original FSA aerial-map footprints.

This is a *diagnostic*: no source pixels become geographic polygons without
independent multi-feature image-registration checks.
"""
import base64
import io
import json
import math
import time
from pathlib import Path

import cv2
import fitz
import numpy as np
import requests
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
REPO_SOURCE=ROOT/"source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT=ROOT/"registration_trials/allendale_grid_search"
OUT.mkdir(parents=True,exist_ok=True)
SERVICE="https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"
ORIGIN=(33.0084896,-81.3224192)
SOURCES={"Tiffany_3779":"Tifanny Loadholt_FSA_Map.pdf","Samuel_3740":"Samuel Lance JR.pdf"}


def image_of_pdf(name):
    with fitz.open(REPO_SOURCE/name) as doc:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(1.7,1.7),colorspace=fitz.csRGB,alpha=False)
        im=Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    w,h=im.size
    out=im.crop((int(w*.025),int(h*.06),int(w*.975),int(h*.79)))
    return cv2.cvtColor(np.asarray(out),cv2.COLOR_RGB2BGR)


def map_bounds(lat,lon,size_m):
    dh=size_m/2/110700
    dw=size_m/2/(111320*math.cos(math.radians(lat)))
    return (lon-dw,lat-dh,lon+dw,lat+dh)


def get_tile(lat,lon,span=5000,pixels=1600):
    bbox=map_bounds(lat,lon,span)
    params={"bbox":",".join(f"{v:.9f}" for v in bbox),"bboxSR":4326,"imageSR":4326,
            "size":f"{pixels},{pixels}","format":"jpg","f":"image"}
    r=requests.get(SERVICE,params=params,timeout=45)
    r.raise_for_status()
    x=cv2.cvtColor(np.asarray(Image.open(io.BytesIO(r.content)).convert("RGB")),cv2.COLOR_RGB2BGR)
    return x,bbox


SIFT=cv2.SIFT_create(nfeatures=6000,contrastThreshold=.015)
CLAHE=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8))


def features(x):
    gray=CLAHE.apply(cv2.cvtColor(x,cv2.COLOR_BGR2GRAY))
    k,d=SIFT.detectAndCompute(gray,None)
    return k,d


def candidate(fa,fb):
    ka,da=fa;kb,db=fb
    if da is None or db is None:return {"good":0,"inliers":0},None
    matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=5),dict(checks=50))
    matches=matcher.knnMatch(da,db,k=2)
    good=[m for m,n in matches if m.distance < .77*n.distance]
    info={"good":len(good),"inliers":0}
    if len(good)<10:return info,None
    src=np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst=np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    H,mask=cv2.findHomography(src,dst,cv2.RANSAC,7.0,maxIters=5000,confidence=.998)
    if H is None:return info,None
    valid=mask.ravel().astype(bool)
    n=int(valid.sum())
    info["inliers"]=n
    info["fraction"]=round(n/len(good),3)
    if n>4:
        pa=src[valid].reshape(-1,2)
        pb=dst[valid].reshape(-1,2)
        est=cv2.perspectiveTransform(pa.reshape(-1,1,2),H).reshape(-1,2)
        info["rmse_px"]=round(float(np.sqrt(np.mean(np.sum((est-pb)**2,axis=1)))),2)
        info["spread_source_px"]=round(float(np.linalg.norm(np.ptp(pa,axis=0))),1)
        info["spread_target_px"]=round(float(np.linalg.norm(np.ptp(pb,axis=0))),1)
    return info,H


def preview(name,photo,tile,H,metrics):
    out=tile.copy()
    if H is not None:
        h,w=photo.shape[:2]
        src=np.float32([[[0,0]],[[w,0]],[[w,h]],[[0,h]]])
        pts=cv2.perspectiveTransform(src,H)
        cv2.polylines(out,[np.int32(pts)],True,(0,255,255),4)
    cv2.putText(out,f"{name}: {metrics['inliers']} inliers",(30,60),cv2.FONT_HERSHEY_SIMPLEX,1.2,(255,255,255),4,cv2.LINE_AA)
    h,w=out.shape[:2]
    if w>1250:out=cv2.resize(out,(1250,int(h*1250/w)),interpolation=cv2.INTER_AREA)
    yes,enc=cv2.imencode('.jpg',out,[cv2.IMWRITE_JPEG_QUALITY,72]);assert yes
    (OUT/(name+'.jpg.b64.txt')).write_text(base64.b64encode(enc).decode('ascii'))


def main():
    raw={name:image_of_pdf(pdf) for name,pdf in SOURCES.items()}
    src={k:features(v) for k,v in raw.items()}
    grid=sorted(((x,y) for x in range(-16000,16001,4000) for y in range(-16000,16001,4000)),key=lambda p:p[0]**2+p[1]**2)
    ranked={k:[] for k in raw};failures=[]
    for i,(east,north) in enumerate(grid):
        lat=ORIGIN[0]+north/110700
        lon=ORIGIN[1]+east/(111320*math.cos(math.radians(ORIGIN[0])))
        try:tile,bbox=get_tile(lat,lon)
        except Exception as exc:
            failures.append({"east_m":east,"north_m":north,"error":str(exc)[:180]})
            continue
        fb=features(tile)
        for name in raw:
            metrics,H=candidate(src[name],fb)
            rec={"name":name,"east_m":east,"north_m":north,"bounds":bbox,**metrics}
            if H is not None:
                rec["homography"]=np.round(H,7).tolist()
            ranked[name].append(rec)
            # Only retain previews for independently plausible correspondence sets.
            if metrics['inliers']>=12 and metrics.get('spread_source_px',0)>120:
                preview(f"{name}_{east:+d}_{north:+d}",raw[name],tile,H,metrics)
        if (i+1)%10==0:
            print("PROGRESS",i+1,"/",len(grid),"best",{k:max((r['inliers'] for r in v),default=0) for k,v in ranked.items()},flush=True)
    output={"origin":ORIGIN,"grid_count":len(grid),"failed_tiles":failures,
            "best_candidates":{k:sorted(v,key=lambda r:(r['inliers'],r['good']),reverse=True)[:15] for k,v in ranked.items()}}
    (OUT/'search_metrics.json').write_text(json.dumps(output,indent=2))
    print("SUMMARY",json.dumps({k:[(r['inliers'],r['east_m'],r['north_m']) for r in val[:5]] for k,val in output['best_candidates'].items()}),flush=True)


if __name__=='__main__':main()
