"""Find the JPEG-only Farm13618/Tract3260 map in nearby independent NAIP.

Diagnostic only: preserve the homography and photo-to-satellite overlay for
practical Field17/Field26 tracing. Never substitute GPS for real field geometry.
"""
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,math
from pathlib import Path
import cv2,numpy as np
from orangeburg_registration_pilot import SOURCE,OUT,SIZE,SPAN,STEP,R,DETECT,prepare,get_tile,register,strip_result

FILENAME='Rosa_Berry_FSA_Map.jpeg'
URL='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
LAT,LON=33.409854,-80.744235
OFFSETS=[(x,y) for x in (-6,-4,-2,0,2,4,6) for y in (-6,-4,-2,0,2,4,6)]

im=cv2.imread(str(SOURCE/FILENAME))
if im is None:raise FileNotFoundError('Rosa farm source JPEG was not fetched from LFS')
hh,ww=im.shape[:2]
print('SOURCE',FILENAME,'shape',ww,hh,flush=True)
views=[]
for name,(x0,y0,x1,y1) in [('left',(70,180,2200,2180)),('right',(1650,150,3970,2180)),('whole',(100,160,3930,2280))]:
    crop=im[y0:y1,x0:x1]
    scale=min(1.,1100/max(crop.shape[:2]))
    if scale<1:crop=cv2.resize(crop,None,fx=scale,fy=scale)
    k,d=DETECT.detectAndCompute(prepare(crop),None)
    if d is not None and len(k)>90:views.append((name,crop,k,d))
best=None
with ThreadPoolExecutor(max_workers=8) as pool:
    future={pool.submit(get_tile,LON,LAT,URL,dx,dy):(dx,dy) for dx,dy in OFFSETS}
    for f in as_completed(future):
        dx,dy=future[f]
        try:tile=f.result()
        except Exception:tile=None
        if tile is None:continue
        for v in views:
            g=register(v,tile)
            if not g.get('nondegenerate_geographic_match_candidate'):continue
            if g['inliers']<45 or g['rmse_px']>2.5 or min(g['image_spread_px'])<85:continue
            if best is None or g['score']>best['g']['score']:best={'v':v,'g':g,'img':tile,'offset':[dx,dy]}
report={'farm_id':'13618','tract_id':'3260','field_ids':['17','26'],'source_file':FILENAME,'status':'NO_CONFIDENT_JPEG_REGISTRATION','search_tiles':len(OFFSETS)}
if best:
    v=best['v'];g=best['g'];tile=best['img'];dx,dy=best['offset']
    x=R*math.radians(LON)+dx*STEP;y=R*math.log(math.tan(math.pi/4+math.radians(LAT)/2))+dy*STEP
    box=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
    cv2.imwrite(str(OUT/'orangeburg_rosa13618_registered_source.jpg'),v[1])
    cv2.imwrite(str(OUT/'orangeburg_rosa13618_satellite.jpg'),tile)
    warped=cv2.warpPerspective(v[1],g['H'],(SIZE,SIZE));mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),g['H'],(SIZE,SIZE))
    overlay=cv2.addWeighted(tile,.65,warped,.35,0);overlay[mask==0]=tile[mask==0]
    cv2.imwrite(str(OUT/'orangeburg_rosa13618_registration_overlay.jpg'),overlay)
    report.update(status='CANDIDATE_GEOMETRIC_JPEG_REGISTRATION_NEEDS_SOURCE_TRACING',
                  source_crop=v[0],source_size_wh=[v[1].shape[1],v[1].shape[0]],
                  tile_bbox_epsg3857=box,tile_size_wh=[SIZE,SIZE],
                  homography_source_to_satellite=g['H'].tolist(),registration=strip_result(g))
    print('MATCH',v[0],g['inliers'],g['rmse_px'],'px',flush=True)
else:print('NO_MATCH for Rosa: no inferred polygons accepted',flush=True)
(OUT/'orangeburg_rosa13618_image_registration.json').write_text(json.dumps(report,indent=2)+'\n')
