"""Bounded image-registration test for Marlboro, York, Charleston FSA maps.

Registration results are evidence only; no unverified polygon is written.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json
import math
import sys

import cv2
import fitz
import numpy as np

from orangeburg_registration_pilot import DETECT, get_tile, register, strip_result, R, SPAN, STEP, SIZE

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'source_recovered/unpacked/SC State_AMP_FSA MAP'
OUT = ROOT / 'analysis/three_county_20261106'
OUT.mkdir(parents=True, exist_ok=True)
ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export'
NAIP = 'https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
TARGETS = [
    ('Marlboro', '3776', 'Johnie Thomas_FSA_Map.pdf', 1, -79.8616282, 34.7554972),
    ('York', '4330', 'Rick Boswell.pdf', 1, -81.2212065, 35.0891533),
    ('Charleston', '1436', 'Keesha Jenkins_FSA_Map.pdf', 1, -79.736953, 32.895935),
    ('Charleston', '1134', 'Sharon Taylor_Farm_FSA_Map.pdf', 1, -80.3267275, 32.6485761),
]


def source_views(file, page):
    doc=fitz.open(file)
    p=doc[page-1]
    scale=min(1.8, 1900/max(p.rect.width,p.rect.height))
    pix=p.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
    whole=cv2.imdecode(np.frombuffer(pix.tobytes('png'),np.uint8),cv2.IMREAD_COLOR)
    h,w=whole.shape[:2]
    result=[]
    for label,frac in [('full',(0.03,0.06,.97,.88)),('map',(0.025,.07,.96,.78)),
                       ('inner',(.075,.12,.90,.72))]:
        x0,y0,x1,y1=frac
        left,top,right,bottom=[int(v) for v in (x0*w,y0*h,x1*w,y1*h)]
        crop=whole[top:bottom,left:right]
        k=min(1.0,1100/max(crop.shape[:2]))
        if k<1:crop=cv2.resize(crop,None,fx=k,fy=k)
        kp,desc=DETECT.detectAndCompute(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),None)
        if desc is None or len(kp)<40:continue
        transform=np.array([[k*scale,0,-k*left],[0,k*scale,-k*top],[0,0,1]],dtype=float)
        result.append((label,crop,kp,desc,transform))
    return whole,scale,result


def process(target):
    county,farm,name,page,lon,lat=target
    f=SRC/name
    if not f.exists():return {'county':county,'farm_id':farm,'status':'FSA_PDF_MISSING'}
    whole,scale,views=source_views(f,page)
    cv2.imwrite(str(OUT/f'{county}_{farm}_source.jpg'),whole)
    if not views:return {'county':county,'farm_id':farm,'status':'NO_SOURCE_FEATURES'}
    # Neighborhood-only search; no open-ended hours-long search.
    offsets=[(0,0),(0,1),(1,0),(0,-1),(-1,0),(1,1),(-1,-1),(1,-1),(-1,1)]
    jobs=[(provider,dx,dy) for provider in (ESRI,NAIP) for dx,dy in offsets]
    best=None
    print('START',county,farm,'source variants',len(views),'tiles',len(jobs),flush=True)
    with ThreadPoolExecutor(max_workers=7) as pool:
        future={pool.submit(get_tile,lon,lat,url,dx,dy):(url,dx,dy) for url,dx,dy in jobs}
        for ft in as_completed(future):
            url,dx,dy=future[ft]
            try:tile=ft.result()
            except Exception:tile=None
            if tile is None:continue
            for view in views:
                match=register(view,tile)
                if match.get('score',0)<=0:continue
                if best is None or (match.get('nondegenerate_geographic_match_candidate',False),match['score']) > (best[3].get('nondegenerate_geographic_match_candidate',False),best[3]['score']):
                    best=(view,tile,(url,dx,dy),match)
    base={'county':county,'farm_id':farm,'source_pdf':name,
          'source_page':page,'reported_anchor_lonlat':[lon,lat]}
    if best is None:
        print('NO_MATCH',county,farm,flush=True)
        return dict(base,status='NO_RASTER_REGISTRATION_EVIDENCE')
    view,tile,(url,dx,dy),match=best
    x=R*math.radians(lon)+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*STEP
    T=match['H']@view[4]
    T/=T[2,2]
    cv2.imwrite(str(OUT/f'{county}_{farm}_match_target.jpg'),tile)
    warped=cv2.warpPerspective(view[1],match['H'],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.ones(view[1].shape[:2],np.uint8)*255,match['H'],(SIZE,SIZE))
    overlay=cv2.addWeighted(tile,.62,warped,.38,0)
    overlay[mask==0]=tile[mask==0]
    cv2.imwrite(str(OUT/f'{county}_{farm}_overlay.jpg'),overlay)
    good=match.get('nondegenerate_geographic_match_candidate',False) and match['inliers']>=38 and match['rmse_px']<=3.5
    status='POTENTIAL_REGISTRATION_NEEDS_FIELD_TRACE' if good else 'WEAK_ALIGNMENT_NEEDS_REVIEW'
    print('RESULT',county,farm,status,'inliers',match['inliers'],'rmse',match['rmse_px'],flush=True)
    return dict(base,status=status,source_render_scale=scale,
                source_full_width_height=list(whole.shape[1::-1]),
                tile_bbox_epsg3857=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2],
                tile_size_wh=[SIZE,SIZE],
                source_render_to_tile_homography=T.tolist(),
                tile_provider='ESRI' if url==ESRI else 'NAIP',
                matched_offset=[dx,dy],registration=strip_result(match))


def main():
    results=[]
    for target in TARGETS:
        if len(sys.argv)>1 and target[0] not in sys.argv[1:]:continue
        results.append(process(target))
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print('DONE',[(r['county'],r['farm_id'],r['status']) for r in results],flush=True)


if __name__=='__main__':main()
