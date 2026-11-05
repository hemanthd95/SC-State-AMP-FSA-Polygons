"""One-pass FSA map alignment for the four Darlington AMP field entries.

Reuses the established SIFT image matcher. Source pages are selected explicitly:
Marva Jackson page 2 and Garrett Patterson page 6 (the preceding five pages
are enrollment forms). Writes diagnostics, not fabricated field geometries.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import math
import time

import cv2
import fitz
import numpy as np

from orangeburg_registration_pilot import (
    R, SIZE, SPAN, STEP, DETECT, prepare, get_tile, register, strip_result,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
OUT = ROOT / 'analysis'
NAIP = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'
TARGETS = [
    ('10262', 'Mava Jackson_FSA map, (dragged).pdf', 2, 34.2960295, -80.0191617),
    ('7370', 'Garrett Patterson_FSA_MAP.pdf', 6, 34.1574677, -80.1402238),
]
FRACS = [(0.06, 0.05, 0.94, 0.77), (0.10, 0.13, 0.90, 0.75),
         (0.02, 0.05, 0.98, 0.84)]
OFFSETS = [(x, y) for x in (-2, -1, 0, 1, 2) for y in (-2, -1, 0, 1, 2)]


def views(pdf, page_number):
    with fitz.open(pdf) as doc:
        page = doc[page_number-1]
        scale = min(1.4, 2800/max(page.rect.width, page.rect.height))
        pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale),
                              colorspace=fitz.csRGB,alpha=False)
        full = cv2.imdecode(np.frombuffer(pix.tobytes('png'),np.uint8),cv2.IMREAD_COLOR)
    hh,ww = full.shape[:2]
    produced = []
    for i,(x0,y0,x1,y1) in enumerate(FRACS):
        left,top,right,bottom = (int(x0*ww),int(y0*hh),int(x1*ww),int(y1*hh))
        crop = full[top:bottom,left:right]
        factor = min(1,1100/max(crop.shape[:2]))
        if factor < 1:crop = cv2.resize(crop,None,fx=factor,fy=factor)
        key,desc = DETECT.detectAndCompute(prepare(crop),None)
        if desc is None or len(key) < 80:continue
        # Source normalized full-page pixel -> cropped matcher pixel.
        transform = [[factor*ww,0,-factor*left],[0,factor*hh,-factor*top],[0,0,1]]
        produced.append((f'p{page_number}_crop{i+1}',crop,key,desc,transform,full))
    return produced


def plausible(match):
    return (match.get('nondegenerate_geographic_match_candidate',False)
            and match['inliers']>=42 and match['rmse_px']<3
            and min(match['source_spread_px'])>110
            and min(match['image_spread_px'])>65)


def one(fid,pdf,page,lat,lon):
    source=SOURCE/pdf
    if not source.exists():return {'farm_id':fid,'status':'FSA_PDF_MISSING'}
    vs=views(source,page)
    print('START',fid,'page',page,'source variants',len(vs),flush=True)
    if not vs:return {'farm_id':fid,'status':'NO_MAP_IMAGE_FEATURES'}
    best=None
    # Process a small region around the supplied field/address hint.
    jobs = [(URL,dx,dy) for URL in (NAIP,ESRI) for dx,dy in OFFSETS]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(get_tile,lon,lat,url,dx,dy):(url,dx,dy)
                 for url,dx,dy in jobs}
        for fut in as_completed(futures):
            url,dx,dy=futures[fut]
            try:tile=fut.result()
            except Exception:tile=None
            if tile is None:continue
            for v in vs:
                result=register(v[:4],tile)
                if not plausible(result):continue
                if best is None or result['score']>best['match']['score']:
                    best={'view':v,'tile':tile,'match':result,'url':url,'dx':dx,'dy':dy}
    if best is None:
        print('NO_CONFIDENT_MATCH',fid,flush=True)
        return {'farm_id':fid,'source_pdf':pdf,'source_page':page,
                'status':'FSA_PDF_PRESENT_GEOGRAPHIC_ALIGNMENT_PENDING',
                'searched_tiles':len(jobs),'hint_latlon':[lat,lon]}
    v=best['view'];tile=best['tile'];m=best['match']
    x=R*math.radians(lon)+best['dx']*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+best['dy']*STEP
    box=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
    transform=m['H']@np.asarray(v[4],dtype=float)
    transform /= transform[2,2]
    cv2.imwrite(str(OUT/f'darlington_{fid}_fsa_page.jpg'),v[5])
    cv2.imwrite(str(OUT/f'darlington_{fid}_naip_match.jpg'),tile)
    warped=cv2.warpPerspective(v[1],m['H'],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.ones(v[1].shape[:2],np.uint8)*255,m['H'],(SIZE,SIZE))
    overlay=cv2.addWeighted(tile,.60,warped,.40,0)
    overlay[mask==0]=tile[mask==0]
    cv2.imwrite(str(OUT/f'darlington_{fid}_overlay.jpg'),overlay)
    print('MATCH',fid,'inliers',m['inliers'],'rmse',m['rmse_px'],flush=True)
    return {'farm_id':fid,'source_pdf':pdf,'source_page':page,
            'status':'IMAGE_ALIGNMENT_CANDIDATE_NEEDS_FIELD_TRACE',
            'source_view':v[0],'source_full_width_height':[v[5].shape[1],v[5].shape[0]],
            'source_normalized_to_tile_homography':transform.tolist(),
            'tile_bbox_epsg3857':box,'tile_size_wh':[SIZE,SIZE],
            'tile_provider':'USGS NAIP' if best['url']==NAIP else 'Esri World Imagery',
            'registration':strip_result(m)}


def main():
    OUT.mkdir(exist_ok=True)
    results=[]
    for args in TARGETS:results.append(one(*args))
    (OUT/'darlington_registration_findings.json').write_text(json.dumps({
        'purpose':'Identify Darlington field placements, not fabricate polygons',
        'results':results},indent=2)+'\n')
    print('COMPLETE',[(r['farm_id'],r['status']) for r in results],flush=True)


if __name__=='__main__':main()
