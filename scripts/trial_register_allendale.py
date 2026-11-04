#!/usr/bin/env python3
"""Diagnostic: locate scanned Allendale FSA aerial maps in official NAIP imagery.

No spatial feature is published unless independent matches meet the QA gates.
"""
import base64
import io
import json
import math
from pathlib import Path

import cv2
import fitz
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
REPO_SOURCE = ROOT / "source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP"
OUT = ROOT / "registration_trials/allendale"
OUT.mkdir(parents=True, exist_ok=True)

SOURCES = {
    "Tiffany_3779": "Tifanny Loadholt_FSA_Map.pdf",
    "Samuel_3740": "Samuel Lance JR.pdf",
}
CENTER_LAT = 33.0084896
CENTER_LON = -81.3224192
SERVICE = "https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage"


def fsa_photo(pdf):
    with fitz.open(REPO_SOURCE / pdf) as doc:
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.8, 1.8), colorspace=fitz.csRGB, alpha=False)
        image = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    # The photographs have crop-year and FSA legend after the map: keep aerial only.
    w, h = image.size
    crop = image.crop((int(w * .025), int(h * .060), int(w * .975), int(h * .790)))
    return cv2.cvtColor(np.asarray(crop), cv2.COLOR_RGB2BGR)


def naip_tile(span_m, size=1900):
    half_lat = (span_m / 2) / 110700
    half_lon = (span_m / 2) / (111320 * math.cos(math.radians(CENTER_LAT)))
    bounds = (CENTER_LON-half_lon, CENTER_LAT-half_lat, CENTER_LON+half_lon, CENTER_LAT+half_lat)
    params = {"bbox": ",".join(f"{v:.9f}" for v in bounds), "bboxSR":4326,
              "imageSR":4326, "size": f"{size},{size}", "format":"jpg", "f":"image"}
    response = requests.get(SERVICE, params=params, timeout=90)
    response.raise_for_status()
    image = Image.open(io.BytesIO(response.content)).convert("RGB")
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR), bounds


def image_register(photo, naip):
    s = cv2.SIFT_create(nfeatures=5500, contrastThreshold=0.02)
    def prep(x):
        g = cv2.cvtColor(x, cv2.COLOR_BGR2GRAY)
        return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(g)
    a, d1 = s.detectAndCompute(prep(photo), None)
    b, d2 = s.detectAndCompute(prep(naip), None)
    if d1 is None or d2 is None:
        return {"keypoints_source":len(a),"keypoints_target":len(b),"good_matches":0,"inliers":0},None,[]
    matches = cv2.BFMatcher(cv2.NORM_L2).knnMatch(d1,d2,k=2)
    good = [m for m,n in matches if m.distance < 0.70*n.distance]
    metric = {"keypoints_source":len(a),"keypoints_target":len(b),"good_matches":len(good)}
    if len(good) < 8:
        metric["inliers"] = 0
        return metric,None,[]
    src = np.float32([a[m.queryIdx].pt for m in good]).reshape(-1,1,2)
    dst = np.float32([b[m.trainIdx].pt for m in good]).reshape(-1,1,2)
    H,mask = cv2.findHomography(src,dst,cv2.RANSAC,7.0,maxIters=10000,confidence=0.999)
    if H is None:
        metric["inliers"] = 0
        return metric,None,[]
    inliers = mask.ravel().astype(bool)
    n = int(inliers.sum())
    metric["inliers"] = n
    metric["inlier_fraction"] = round(n/len(good),3)
    if n:
        pred = cv2.perspectiveTransform(src[inliers].reshape(-1,1,2),H).reshape(-1,2)
        truth = dst[inliers].reshape(-1,2)
        metric["inlier_rmse_px"] = round(float(np.sqrt(np.mean(np.sum((pred-truth)**2,axis=1)))),2)
    pts = [(tuple(map(int,a[m.queryIdx].pt)),tuple(map(int,b[m.trainIdx].pt))) for i,m in enumerate(good) if inliers[i]]
    return metric,H,pts


def write_preview(name,image,quality=67,max_width=1200):
    h,w = image.shape[:2]
    if w > max_width:
        image = cv2.resize(image,(max_width,int(h*max_width/w)),interpolation=cv2.INTER_AREA)
    okay,data=cv2.imencode(".jpg",image,[cv2.IMWRITE_JPEG_QUALITY,quality])
    assert okay
    (OUT/(name+".jpg.b64.txt")).write_text(base64.b64encode(data).decode("ascii"))
    return len(data)


def main():
    results = []
    photos = {name:fsa_photo(path) for name,path in SOURCES.items()}
    for name,photo in photos.items():
        write_preview(name+"_fsa_photo",photo)
    for radius in (1500,3000,6000,12000):
        try:
            tile,bounds=naip_tile(radius)
        except Exception as exc:
            results.append({"span_m":radius,"error":str(exc)})
            continue
        write_preview("naip_span_"+str(radius),tile)
        for name,photo in photos.items():
            metrics,H,pts=image_register(photo,tile)
            result={"farm":name,"span_m":radius,"bounds":bounds,**metrics}
            if H is not None:
                result["homography"] = np.asarray(H).round(7).tolist()
            results.append(result)
            if H is not None and len(pts)>=10:
                display=tile.copy()
                cv2.polylines(display,[np.int32(cv2.perspectiveTransform(
                    np.float32([[[0,0]],[[photo.shape[1],0]],[[photo.shape[1],photo.shape[0]]],[[0,photo.shape[0]]]]),H))],True,(0,255,255),3)
                for p,q in pts:
                    cv2.circle(display,q,4,(0,255,255),-1)
                write_preview(name+"_span_"+str(radius)+"_matched",display)
            print(json.dumps(result),flush=True)
    (OUT/"registration_metrics.json").write_text(json.dumps(results,indent=2))


if __name__=="__main__":
    main()
