"""Find genuine target-page matches for Montez and Tywone Hillard.

The strongest registration in a multi-page FSA PDF can belong to a DIFFERENT
farm. Only p1 is matched here because the identifiers have been visually read:
Farm1033/Tract3879/Field4 and Farm3873/Tract3895/Fields1,4.
This is diagnostic. No polygons are accepted without subsequent tracing/QA.
"""
import json, math
from concurrent.futures import ThreadPoolExecutor,as_completed
import cv2,numpy as np
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,STEP,SIZE,source_views,get_tile,register,strip_result,SERVICES

inventory=json.loads((OUT/'orangeburg_source_inventory.json').read_text())
tasks=[('1033','3879',['4']),('3873','3895',['1','4'])]
offsets=[(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1),(2,0),(-2,0),(0,2),(0,-2)]
reports=[]
for fid,tract,fields in tasks:
    meta=inventory['farms'][fid]
    src=meta['candidate_fsa_pdf_sources'][0]['path']
    p1=[v for v in source_views(SOURCE/src) if v[0].startswith('p1_')]
    loc=meta['spreadsheet_coordinate_hints'][0]
    if not p1:raise RuntimeError('No p1 map view for '+fid)
    best=None
    jobs=[(kind,url,dx,dy) for kind,url in SERVICES for dx,dy in offsets]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures={pool.submit(get_tile,loc['longitude'],loc['latitude'],url,dx,dy):(kind,dx,dy) for kind,url,dx,dy in jobs}
        for future in as_completed(futures):
            name,dx,dy=futures[future]
            try:img=future.result()
            except Exception:img=None
            if img is None:continue
            for view in p1:
                reg=register(view,img)
                if not reg.get('nondegenerate_geographic_match_candidate'):continue
                score=reg['score']
                if best is None or score>best['score']:
                    best={'score':score,'view':view,'image':img,'registration':reg,
                          'provider':name,'offset':[dx,dy]}
    row={'farm_id':fid,'tract_id':tract,'target_fields':fields,'source_pdf':src,
         'source_page':1,'candidate_only':True}
    if best is None:
        row['status']='NO_RELIABLE_PAGE1_REGISTRATION_FOUND'
        print('NO RELIABLE MATCH FOR',fid,flush=True)
    else:
        view=best['view'];img=best['image'];reg=best['registration'];dx,dy=best['offset']
        x=R*math.radians(loc['longitude'])+dx*STEP
        y=R*math.log(math.tan(math.pi/4+math.radians(loc['latitude'])/2))+dy*STEP
        bounds=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
        row.update(status='P1_GEOMETRIC_REGISTRATION_CANDIDATE_AWAIT_FIELD_QA',
                   provider=best['provider'],offset_dx_dy=best['offset'],view=view[0],
                   view_size_wh=[view[1].shape[1],view[1].shape[0]],
                   tile_bbox_epsg3857=bounds,tile_size_wh=[SIZE,SIZE],
                   homography_source_view_to_tile_px=reg['H'].tolist(),
                   registration=strip_result(reg))
        cv2.imwrite(str(OUT/f'orangeburg_target_p1_farm{fid}_source.jpg'),view[1])
        cv2.imwrite(str(OUT/f'orangeburg_target_p1_farm{fid}_naip.jpg'),img)
        warped=cv2.warpPerspective(view[1],reg['H'],(SIZE,SIZE))
        footprint=cv2.warpPerspective(np.full(view[1].shape[:2],255,np.uint8),reg['H'],(SIZE,SIZE))
        overlay=cv2.addWeighted(img,.67,warped,.33,0)
        overlay[footprint==0]=img[footprint==0]
        cv2.imwrite(str(OUT/f'orangeburg_target_p1_farm{fid}_overlay.jpg'),overlay)
        print('PAGE1 VERIFIED MAP CANDIDATE',fid,view[0],best['provider'],
              best['offset'],'INLIERS',reg['inliers'],'RMSE',reg['rmse_px'],flush=True)
    reports.append(row)
(OUT/'orangeburg_target_page_registrations.json').write_text(json.dumps({
    'status':'TARGET_PAGE_REGISTRATION_DIAGNOSTICS_NOT_YET_ACCEPTED_POLYGONS',
    'scope':'Only source pages confirmed to depict the workbook Farm/Tract/Field',
    'results':reports},indent=2)+'\n')
