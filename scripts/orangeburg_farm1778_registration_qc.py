"""Diagnose precise Farm 1778 / Tract 1334 image registration and FSA yellow field outlines.

Diagnostics only. Never release a polygon without targeted field-boundary QA.
"""
import json,math
from pathlib import Path
import cv2,numpy as np
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,STEP,SIZE,source_views,get_tile,register

INV=json.loads((ROOT/'analysis/orangeburg_source_inventory.json').read_text())
F=INV['farms']['1778']
PDF=SOURCE/F['candidate_fsa_pdf_sources'][0]['path']
hint=F['spreadsheet_coordinate_hints'][0]
views=source_views(PDF)
view=next(v for v in views if v[0]=='p1_c2')
url='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
aerial=get_tile(hint['longitude'],hint['latitude'],url,0,0)
if aerial is None:raise RuntimeError('USGS NAIP map request failed')
result=register(view,aerial)
if not result.get('nondegenerate_geographic_match_candidate'):
    raise RuntimeError('Failed conservative image registration: '+repr({k:v for k,v in result.items() if k not in ('good_matches','inlier_mask','source_keypoints','target_keypoints','H')}))
H=result['H']
x=R*math.radians(hint['longitude'])
y=R*math.log(math.tan(math.pi/4+math.radians(hint['latitude'])/2))
bbox=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
source=view[1]
cv2.imwrite(str(OUT/'orangeburg_farm1778_source_registration_view.jpg'),source,[cv2.IMWRITE_JPEG_QUALITY,90])
cv2.imwrite(str(OUT/'orangeburg_farm1778_satellite_registration_view.jpg'),aerial,[cv2.IMWRITE_JPEG_QUALITY,90])
warp=cv2.warpPerspective(source,H,(SIZE,SIZE),flags=cv2.INTER_LINEAR)
valid=cv2.warpPerspective(np.full(source.shape[:2],255,np.uint8),H,(SIZE,SIZE))
layer=cv2.addWeighted(aerial,.55,warp,.45,0)
layer[valid==0]=aerial[valid==0]
cv2.imwrite(str(OUT/'orangeburg_farm1778_aerial_registration_overlay.jpg'),layer,[cv2.IMWRITE_JPEG_QUALITY,90])

# Yellow outline diagnostic; preserve all candidate regions for manual polygon selection.
blue,green,red=cv2.split(source)
yellow=((red>150)&(green>145)&(blue<125)&
        (red.astype(np.float32)>blue.astype(np.float32)*1.4)&
        (green.astype(np.float32)>blue.astype(np.float32)*1.4)).astype(np.uint8)*255
yellow=cv2.morphologyEx(yellow,cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
cv2.imwrite(str(OUT/'orangeburg_farm1778_yellow_boundaries_mask.png'),yellow)
segments=cv2.connectedComponentsWithStats(255-yellow,connectivity=8)
num,lab,stats,centers=segments
cells=[{'label':int(i),'bbox_xywh':list(map(int,stats[i][:4])),
        'pixel_area':int(stats[i,cv2.CC_STAT_AREA]),
        'centroid_xy':[round(float(v),1) for v in centers[i]]}
       for i in range(1,num) if stats[i,cv2.CC_STAT_AREA]>200]
cells.sort(key=lambda d:-d['pixel_area'])
output={'status':'GEOREGISTRATION_CONFIRMED_FIELD_OUTLINE_UNDER_REVIEW',
        'farm_id':'1778','tract_id':'1334','target_field_id':'6',
        'printed_target_field_acres':14.31,'source_view':'p1_c2',
        'source_view_size_wh':[source.shape[1],source.shape[0]],
        'target_tile_size_wh':[SIZE,SIZE],
        'tile_bbox_epsg3857':bbox,
        'homography_source_view_to_tile_px':H.tolist(),
        'registration_metrics':{k:v for k,v in result.items() if k not in ('good_matches','inlier_mask','source_keypoints','target_keypoints','H')},
        'candidate_enclosed_field_regions':cells[:45],
        'warnings':['FSA yellow lines include whole-tract and neighboring fields; only field 6 of tract 1334 is requested.',
                    'Connected-component segmentation is for QC only; do not export a guessed polygon.',
                    'Do not replace current satellite scene with a fake or unlabeled basemap.']}
(OUT/'orangeburg_farm1778_registration_qc.json').write_text(json.dumps(output,indent=2)+'\n')
print('SUCCESS verified aerial registration',result['inliers'],'inliers','regions',len(cells),flush=True)
