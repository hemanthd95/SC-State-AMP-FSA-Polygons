"""Attempt exact Jasper Summers Farm13653/Tract5515 registration, excluding wrong Tract5516.

Only the first printed FSA page matches the spreadsheet tract (5515).
"""
import json,math
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np,cv2
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,STEP,SIZE,SERVICES,source_views,get_tile,register,strip_result

F=json.loads((ROOT/'analysis/orangeburg_source_inventory.json').read_text())['farms']['13653']
pdf=SOURCE/F['candidate_fsa_pdf_sources'][0]['path']
viewlist=[v for v in source_views(pdf) if v[0].startswith('p1_')]
loc=F['spreadsheet_coordinate_hints'][0]
lon,lat=loc['longitude'],loc['latitude']
jobs=[(name,url,dx,dy) for name,url in SERVICES
      for dx,dy in [(0,0),(-1,-1),(-1,0),(0,-1),(1,0),(0,1),(1,1),(-1,1),(1,-1)]]
best=None
with ThreadPoolExecutor(max_workers=5) as pool:
    futs={pool.submit(get_tile,lon,lat,url,dx,dy):(name,dx,dy) for name,url,dx,dy in jobs}
    for fut in as_completed(futs):
        name,dx,dy=futs[fut]
        try:img=fut.result()
        except Exception:continue
        if img is None:continue
        for v in viewlist:
            result=register(v,img)
            if 'score' not in result:continue
            score=(bool(result['nondegenerate_geographic_match_candidate']),result['score'])
            if best is None or score>best[0]:
                best=(score,v,img,result,name,dx,dy)
if best is None:
    report={'farm_id':'13653','tract_id':'5515','status':'NO_GEOMETRIC_MATCH_TO_TARGET_TRACT',
            'warning':'The source second page belongs to Tract5516 and is deliberately excluded'}
else:
    score,v,img,d,provider,dx,dy=best
    report={'farm_id':'13653','tract_id':'5515','field_id':'1','printed_acres':2.58,
            'source_page':1,'source_view':v[0],'imagery_provider':provider,
            'tile_offsets':[dx,dy],'registration_metrics':strip_result(d),
            'status':'TRACT_5515_REGISTRATION_CANDIDATE' if score[0] else 'NO_ACCEPTED_MATCH_TO_TRACT_5515',
            'warning':'Tract 5516 appears on the second PDF page and is out-of-scope'}
    if score[0]:
        H=d['H']
        x=R*math.radians(lon)+dx*STEP
        y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*STEP
        report.update({'homography_source_view_to_tile_px':H.tolist(),
                       'tile_bbox_epsg3857':[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2],
                       'source_view_size_wh':[v[1].shape[1],v[1].shape[0]],
                       'target_tile_size_wh':[SIZE,SIZE]})
        mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),H,(SIZE,SIZE))
        warped=cv2.warpPerspective(v[1],H,(SIZE,SIZE))
        overlay=cv2.addWeighted(img,.6,warped,.4,0)
        overlay[mask==0]=img[mask==0]
        cv2.imwrite(str(OUT/'orangeburg_farm13653_tract5515_overlay.jpg'),overlay,[cv2.IMWRITE_JPEG_QUALITY,88])
        cv2.imwrite(str(OUT/'orangeburg_farm13653_tract5515_source.jpg'),v[1],[cv2.IMWRITE_JPEG_QUALITY,88])
(OUT/'orangeburg_farm13653_tract5515_registration.json').write_text(json.dumps(report,indent=2)+'\n')
print('JASPER TRACT5515',report['status'],report.get('registration_metrics',{}).get('inliers'),flush=True)
