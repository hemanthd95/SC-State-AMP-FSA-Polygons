"""Search a broad rural envelope for Marion Farm 9652 scanned FSA imagery.

Because the spreadsheet location may be a producer mailing address, searching
the immediate point is insufficient. Tests genuine aerial feature matches;
never labels a spatial prediction a real farm without robust registration.
"""
from pathlib import Path
import json
import math

import cv2
import numpy as np

from trial_register_florence_marion import DATA,crop_photo,features,tile,compare

ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'registration_trials/albert_wide_search'
OUTPUT.mkdir(parents=True,exist_ok=True)
name='Albert_Vareen_Farm9652'
record=DATA[name]
source=crop_photo(record)
fa=features(source)
cv2.imwrite(str(OUTPUT/'source_scan.jpg'),source,[cv2.IMWRITE_JPEG_QUALITY,85])
lat0,lon0=record['center']

def main():
    offsets=[-8400,-5600,-2800,0,2800,5600,8400]
    grid=sorted([(dx,dy) for dx in offsets for dy in offsets],key=lambda xy:sum(x*x for x in xy))
    results=[];failures=[]
    for i,(dx,dy) in enumerate(grid):
        lat=lat0+dy/110700
        lon=lon0+dx/(111320*math.cos(math.radians(lat0)))
        try:base,bbox,provider=tile(lat,lon,3300)
        except Exception as exc:
            failures.append({'offset_m':[dx,dy],'error':str(exc)[:200]});continue
        score,H=compare(fa,features(base),source.shape,base.shape)
        result={'offset_m':[dx,dy],'bbox':bbox,'provider':provider,**score}
        if H is not None:
            result['H']=np.round(H,9).tolist()
        results.append(result)
        if result['status'].startswith('GEOMETRIC_QA_PASS'):
            q=np.float32([[[0,0]],[[source.shape[1],0]],[[source.shape[1],source.shape[0]]],[[0,source.shape[0]]]])
            v=cv2.perspectiveTransform(q,H)
            preview=base.copy()
            warp=cv2.warpPerspective(source,H,(1500,1500))
            mask=cv2.warpPerspective(np.ones(source.shape[:2],np.uint8)*255,H,(1500,1500))>0
            preview[mask]=((preview[mask].astype(np.uint16)+warp[mask].astype(np.uint16))//2).astype(np.uint8)
            cv2.polylines(preview,[v.astype(np.int32)],True,(0,255,255),4)
            cv2.imwrite(str(OUTPUT/f'candidate_{dx}_{dy}.jpg'),preview,[cv2.IMWRITE_JPEG_QUALITY,78])
        if (i+1)%7==0:
            print('PROGRESS',i+1,'/',len(grid),'best inliers',max((r['inliers'] for r in results),default=0),flush=True)
    results.sort(key=lambda z:(z['status'].startswith('GEOMETRIC_QA_PASS'),z['inliers']),reverse=True)
    (OUTPUT/'candidates.json').write_text(json.dumps({'source':record,'counties':'Marion area around supplied spreadsheet coordinates',
         'searched_tiles':len(grid),'results':results[:30],'failures':failures,
         'warning':'Any apparent match still requires FSA field-edge digitization, area check and independent spatial QA'},indent=2))
    print('BEST',[(x['inliers'],x['status'],x['offset_m']) for x in results[:8]],flush=True)

if __name__=='__main__':main()
