"""Conservative imagery-registration diagnostic for Florence/Marion FSA scans.

Uses source aerial imagery only. This script deliberately does NOT generate
GeoJSON polygons: source-to-NAIP registration must first pass geometric QA.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
import json
import math
from pathlib import Path
import time

import cv2
import fitz
import numpy as np
import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT = ROOT / 'registration_trials/florence_marion'
OUT.mkdir(parents=True, exist_ok=True)
DATA = {
    'June_Bazen_Farm15803': {'pdf': 'June_Bazen_FSA_Map.pdf', 'page': 0,
                           'center': (33.8779153, -79.5664272), 'crop': (.195, .149, .890, .765)},
    'June_Bazen_Farm20119': {'pdf': 'June_Bazen_FSA_Map.pdf', 'page': 1,
                           'center': (33.8779153, -79.5664272), 'crop': (.193, .171, .890, .775)},
    'Shelia_McAllister_Farm20170': {'pdf': 'Juan_McAllister_FSA_Map.pdf', 'page': 0,
                                 'center': (34.0960736, -79.7445063), 'crop': (.031, .066, .955, .771)},
    'Albert_Vareen_Farm9652': {'pdf': 'Albert vareen_FSA_Map.pdf', 'page': 0,
                              'center': (33.792, -79.2745), 'crop': (.031, .064, .911, .752)},
}
SERVICES = [
    ('USGS NAIP', 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'),
    ('Esri World Imagery', 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'),
]
SIFT = cv2.SIFT_create(nfeatures=9000, contrastThreshold=.008, edgeThreshold=16)
CLAHE = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))


def crop_photo(record):
    with fitz.open(SOURCE / record['pdf']) as pdf:
        page = pdf[record['page']]
        # 1600 px height for an 11-inch page; monochrome crop retained.
        matrix = fitz.Matrix(1.85, 1.85) if page.rect.height < 1000 else fitz.Matrix(.42,.42)
        pix = page.get_pixmap(matrix=matrix, colorspace=fitz.csRGB, alpha=False)
        rgb = np.array(Image.open(BytesIO(pix.tobytes('png'))).convert('RGB'))
    h,w=rgb.shape[:2]
    x0,y0,x1,y1=record['crop']
    rgb=rgb[int(y0*h):int(y1*h),int(x0*w):int(x1*w)]
    if rgb.shape[1]>1500:
        height=round(rgb.shape[0]*1500/rgb.shape[1])
        rgb=cv2.resize(rgb,(1500,height),interpolation=cv2.INTER_AREA)
    return cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)


def features(bgr):
    gray=cv2.cvtColor(bgr,cv2.COLOR_BGR2GRAY)
    gray=CLAHE.apply(gray)
    return SIFT.detectAndCompute(gray,None)


def tile(lat,lon,span,pixels=1500):
    dlat=span/(2*110700);dlon=span/(2*111320*math.cos(math.radians(lat)))
    bbox=(lon-dlon,lat-dlat,lon+dlon,lat+dlat)
    params={'bbox':','.join(f'{v:.8f}' for v in bbox),'bboxSR':4326,
            'imageSR':4326,'size':f'{pixels},{pixels}','format':'jpg','f':'image'}
    errors=[]
    for label,url in SERVICES:
        for _ in range(2):
            try:
                r=requests.get(url,params=params,timeout=50)
                r.raise_for_status()
                rgb=np.array(Image.open(BytesIO(r.content)).convert('RGB'))
                if rgb.shape[:2]!=(pixels,pixels) or np.std(rgb)<13:
                    raise RuntimeError('Empty/wrong-size imagery')
                return cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),bbox,label
            except Exception as exc:
                errors.append(f'{label}: {exc}')
                time.sleep(1)
    raise RuntimeError('; '.join(errors)[:500])


def compare(src_feature,dst_feature,source_shape,target_shape):
    sa,da=src_feature;sb,db=dst_feature
    score={'good':0,'inliers':0,'status':'NO_DESCRIPTORS'}
    if da is None or db is None:return score,None
    matcher=cv2.FlannBasedMatcher(dict(algorithm=1,trees=5),dict(checks=90))
    nn=matcher.knnMatch(da,db,k=2)
    matched=[m for m,n in nn if m.distance<.72*n.distance]
    score['good']=len(matched)
    if len(matched)<12:
        score['status']='INSUFFICIENT_MATCHES';return score,None
    src=np.float32([sa[m.queryIdx].pt for m in matched]).reshape(-1,1,2)
    dst=np.float32([sb[m.trainIdx].pt for m in matched]).reshape(-1,1,2)
    H,mask=cv2.findHomography(src,dst,cv2.USAC_MAGSAC,4.5,maxIters=15000,confidence=.999)
    if H is None or mask is None:
        score['status']='NO_HOMOGRAPHY';return score,None
    valid=mask.ravel().astype(bool)
    n=int(valid.sum());score['inliers']=n
    score['inlier_fraction']=round(n/len(matched),3)
    if n<10:
        score['status']='INSUFFICIENT_INLIERS';return score,None
    pa=src[valid].reshape(-1,2);pb=dst[valid].reshape(-1,2)
    proj=cv2.perspectiveTransform(pa.reshape(-1,1,2),H).reshape(-1,2)
    score['rmse_px']=round(float(np.sqrt(np.mean(np.sum((proj-pb)**2,axis=1)))),2)
    ah,aw=source_shape[:2];bh,bw=target_shape[:2]
    score['source_hull_fraction']=round(float(cv2.contourArea(cv2.convexHull(pa))/(aw*ah)),5)
    score['target_hull_fraction']=round(float(cv2.contourArea(cv2.convexHull(pb))/(bw*bh)),5)
    corner=np.float32([[[0,0]],[[aw-1,0]],[[aw-1,ah-1]],[[0,ah-1]]])
    quad=cv2.perspectiveTransform(corner,H).reshape(-1,2)
    qa=float(abs(cv2.contourArea(quad)))
    score['projected_map_area_fraction']=round(qa/(bw*bh),5)
    score['convex_quad']=bool(cv2.isContourConvex(quad.astype(np.float32)))
    score['projected_bbox_px']=[round(float(v),1) for v in [quad[:,0].min(),quad[:,1].min(),quad[:,0].max(),quad[:,1].max()]]
    passes=(n>=18 and score['rmse_px']<=4.5 and
            score['source_hull_fraction']>.035 and score['target_hull_fraction']>.005 and
            .008<score['projected_map_area_fraction']<.85 and score['convex_quad'] and
            min(quad[:,0])>-bw*.5 and max(quad[:,0])<bw*1.5 and
            min(quad[:,1])>-bh*.5 and max(quad[:,1])<bh*1.5)
    score['status']='GEOMETRIC_QA_PASS__REQUIRES_INDEPENDENT_VALIDATION' if passes else 'GEOMETRIC_QA_FAIL'
    return score,H


def preview(name,photo,base,H,metrics):
    h,w=photo.shape[:2]
    out=base.copy()
    if H is not None:
        corners=np.float32([[[0,0]],[[w,0]],[[w,h]],[[0,h]]])
        q=cv2.perspectiveTransform(corners,H).astype(np.int32)
        cv2.polylines(out,[q],True,(20,240,240),4)
        warp=cv2.warpPerspective(photo,H,(out.shape[1],out.shape[0]))
        mask=cv2.warpPerspective(np.ones((h,w),np.uint8)*180,H,(out.shape[1],out.shape[0]))
        mask=cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR).astype(np.float32)/255.
        out=(np.clip(warp.astype(np.float32)*mask*.55+out.astype(np.float32)*(1-mask*.55),0,255)).astype(np.uint8)
    out=cv2.resize(out,(1000,1000),interpolation=cv2.INTER_AREA)
    cv2.putText(out,name[:36],(20,36),cv2.FONT_HERSHEY_SIMPLEX,.75,(255,255,255),3,cv2.LINE_AA)
    cv2.putText(out,f"{metrics['inliers']} inliers / {metrics['status'][:28]}",(20,68),cv2.FONT_HERSHEY_SIMPLEX,.60,(255,255,255),3,cv2.LINE_AA)
    cv2.imwrite(str(OUT / f'{name}.jpg'),out,[cv2.IMWRITE_JPEG_QUALITY,80])


def main():
    records={name:crop_photo(x) for name,x in DATA.items()}
    feats={k:features(v) for k,v in records.items()}
    for name,img in records.items():cv2.imwrite(str(OUT / f'source_{name}.jpg'),img,[cv2.IMWRITE_JPEG_QUALITY,85])
    grouped=defaultdict(list)
    for name,r in DATA.items():grouped[tuple(r['center'])].append(name)
    results={name:[] for name in DATA};failures=[]
    for center,names in grouped.items():
        lat,lon=center
        # An address may represent the house rather than the FSA field; search
        # a 4-by-4 km envelope before reporting failure, never a fabricated fit.
        offsets=[(0,0),(-1100,0),(1100,0),(0,-1100),(0,1100),(-1100,-1100),(-1100,1100),(1100,-1100),(1100,1100)]
        for dx,dy in offsets:
            new_lat=lat+dy/110700
            new_lon=lon+dx/(111320*math.cos(math.radians(lat)))
            try:basemap,bbox,provider=tile(new_lat,new_lon,2300)
            except Exception as exc:
                failures.append({'names':names,'dx':dx,'dy':dy,'error':str(exc)});continue
            ftarget=features(basemap)
            for name in names:
                s,H=compare(feats[name],ftarget,records[name].shape,basemap.shape)
                result={'offset_m':[dx,dy],'bbox':bbox,'provider':provider,**s}
                if H is not None:result['H']=np.round(H,8).tolist()
                results[name].append(result)
                if result['status'].startswith('GEOMETRIC_QA_PASS'):
                    preview(f'{name}_{dx:+05}_{dy:+05}',records[name],basemap,H,s)
            print('TILE',names,dx,dy,[(n,results[n][-1]['inliers'],results[n][-1]['status']) for n in names],flush=True)
    summary={k:sorted(v,key=lambda r:(r['status'].startswith('GEOMETRIC_QA_PASS'),r['inliers']),reverse=True)[:6] for k,v in results.items()}
    (OUT/'registration_diagnostics.json').write_text(json.dumps({'best_candidates':summary,'failures':failures,
            'note':'Diagnostic only. Pixel matches are not verified polygons. Source FSA acres and geographic road control still required.'},indent=2))
    print('SUMMARY',json.dumps({k:[(r['inliers'],r['status'],r['offset_m']) for r in v[:2]] for k,v in summary.items()}),flush=True)


if __name__=='__main__':main()
