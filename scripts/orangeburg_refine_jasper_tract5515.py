"""Refine Jasper Tract5515 match so the *requested field* is inside the aerial tile.

An initial valid geometry only captured the bottom of the FSA map; this
recenters on the extrapolated field and repeats independent feature matches.
"""
import json,math
from pathlib import Path
import cv2,numpy as np
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,SIZE,SERVICES,source_views,get_tile,register,strip_result

report=json.loads((OUT/'orangeburg_farm13653_tract5515_registration.json').read_text())
if report['status']!='TRACT_5515_REGISTRATION_CANDIDATE':raise RuntimeError('Initial FSA Tract5515 match unavailable')
H=np.array(report['homography_source_view_to_tile_px'])
source_center=np.float32([[[313.,80.]]])
target=cv2.perspectiveTransform(source_center,H)[0][0]
bx=report['tile_bbox_epsg3857']
mx=bx[0]+target[0]/SIZE*(bx[2]-bx[0])
my=bx[3]-target[1]/SIZE*(bx[3]-bx[1])
lon=math.degrees(mx/R);lat=math.degrees(2*math.atan(math.exp(my/R))-math.pi/2)
inv=json.loads((ROOT/'analysis/orangeburg_source_inventory.json').read_text())
pdf=SOURCE/inv['farms']['13653']['candidate_fsa_pdf_sources'][0]['path']
views=[v for v in source_views(pdf) if v[0].startswith('p1_')]
best=None
for provider,url in SERVICES:
    # First recentre exactly where the registration puts tract 5515.
    for dy in [0,1,-1]:
        im=get_tile(lon,lat,url,0,dy)
        if im is None:continue
        for view in views:
            d=register(view,im)
            if 'score' not in d:continue
            spread=d.get('source_spread_px',[0,0])
            pass_strict=(d['nondegenerate_geographic_match_candidate'] and d['inliers']>=90
                         and min(spread)>180 and min(d['image_spread_px'])>180)
            rank=(pass_strict,d['nondegenerate_geographic_match_candidate'],d['score'])
            if best is None or rank>best[0]:best=(rank,view,im,d,provider,dy)
if best is None:
    out={'status':'NO_REFINED_IMAGE_MATCH','farm_id':'13653','tract_id':'5515'}
else:
    rank,v,im,d,provider,dy=best
    pxcenter=R*math.radians(lon)
    pycenter=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*850.
    bbox=[pxcenter-SPAN/2,pycenter-SPAN/2,pxcenter+SPAN/2,pycenter+SPAN/2]
    out={'farm_id':'13653','tract_id':'5515','field_id':'1','fsa_printed_acres':2.58,
         'status':'REFINED_TARGET_FIELD_REGISTRATION_CANDIDATE' if rank[0] else 'REFINEMENT_STILL_INSUFFICIENT',
         'provider':provider,'source_view':v[0],'source_view_size_wh':[v[1].shape[1],v[1].shape[0]],
         'target_tile_size_wh':[SIZE,SIZE],'tile_bbox_epsg3857':bbox,
         'registration_metrics':strip_result(d),'initial_field_extrapolation':[round(lon,7),round(lat,7)],
         'note':'Tract5515 only; never use second source page belonging to Tract5516'}
    if rank[0]:
        out['homography_source_view_to_tile_px']=d['H'].tolist()
        imsrc=v[1]
        valid=cv2.warpPerspective(np.full(imsrc.shape[:2],255,np.uint8),d['H'],(SIZE,SIZE))
        warped=cv2.warpPerspective(imsrc,d['H'],(SIZE,SIZE))
        overlay=cv2.addWeighted(im,.6,warped,.4,0);overlay[valid==0]=im[valid==0]
        cv2.imwrite(str(OUT/'orangeburg_farm13653_tract5515_refined_source.jpg'),imsrc,[cv2.IMWRITE_JPEG_QUALITY,90])
        cv2.imwrite(str(OUT/'orangeburg_farm13653_tract5515_refined_overlay.jpg'),overlay,[cv2.IMWRITE_JPEG_QUALITY,90])
(OUT/'orangeburg_farm13653_tract5515_refinement.json').write_text(json.dumps(out,indent=2)+'\n')
print('REFINED',out['status'],out.get('registration_metrics',{}).get('inliers'),flush=True)
