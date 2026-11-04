"""Register Shannon Lowe Farm 4631 raster FSA field against NAIP near GIS GPS."""
from pathlib import Path
import json
import math

import cv2
import numpy as np

from trial_register_florence_marion import crop_photo,features,tile,compare

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'registration_trials/aiken_shannon'
OUT.mkdir(parents=True,exist_ok=True)
RECORD={'pdf':'Shannon_Lowe_FSA Map.pdf','page':0,'center':(33.4275064,-81.7951119),
        'crop':(.022,.055,.966,.782)}

def main():
    source=crop_photo(RECORD);f=features(source)
    cv2.imwrite(str(OUT/'source_crop.jpg'),source,[cv2.IMWRITE_JPEG_QUALITY,86])
    lat0,lon0=RECORD['center']
    offsets=[(0,0),(-1100,0),(1100,0),(0,-1100),(0,1100),(-1100,-1100),(-1100,1100),(1100,-1100),(1100,1100)]
    records=[]
    for dx,dy in offsets:
        lat=lat0+dy/110700
        lon=lon0+dx/(111320*math.cos(math.radians(lat0)))
        try:base,bbox,provider=tile(lat,lon,2300)
        except Exception as exc:
            print('TILE FAILED',dx,dy,str(exc)[:120],flush=True);continue
        score,H=compare(f,features(base),source.shape,base.shape)
        item={'offset_m':[dx,dy],'bbox':bbox,'provider':provider,**score}
        if H is not None:item['H']=np.round(H,9).tolist()
        records.append(item)
        if item['status'].startswith('GEOMETRIC_QA_PASS'):
            w=base.copy();q=np.float32([[[0,0]],[[source.shape[1],0]],[[source.shape[1],source.shape[0]]],[[0,source.shape[0]]]])
            q=cv2.perspectiveTransform(q,H)
            p=cv2.warpPerspective(source,H,(1500,1500))
            m=cv2.warpPerspective(np.ones(source.shape[:2],np.uint8),H,(1500,1500))>0
            w[m]=((w[m].astype(np.uint16)+p[m].astype(np.uint16))//2).astype(np.uint8)
            cv2.polylines(w,[q.astype(np.int32)],True,(0,255,255),4)
            cv2.imwrite(str(OUT/f'candidate_{dx}_{dy}.jpg'),w,[cv2.IMWRITE_JPEG_QUALITY,80])
        print('PROGRESS',dx,dy,score['good'],score['inliers'],score['status'],flush=True)
    records.sort(key=lambda r:(r['status'].startswith('GEOMETRIC_QA_PASS'),r['inliers']),reverse=True)
    (OUT/'registration.json').write_text(json.dumps({'record':RECORD,'best':records[:9]},indent=2))
    print('BEST',[(r['inliers'],r['status'],r['offset_m']) for r in records[:5]],flush=True)

if __name__=='__main__':main()
