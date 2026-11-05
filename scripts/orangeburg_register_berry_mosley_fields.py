"""Store exact-map homographies and source crops for two promising Orangeburg farms.

Farm14048/Tract46008/Field1 and Farm11782/Tract6230/Field13.
No polygon is accepted until field boundaries and acreage are reviewed.
"""
import json,math
from pathlib import Path
import numpy as np,cv2
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,STEP,SIZE,source_views,get_tile,register,strip_result
INV=json.loads((OUT/'orangeburg_source_inventory.json').read_text())
URL='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
TASKS=[('14048','46008','1',.89,(0,0)),('11782','6230','13',7.53,(1,1))]
for fid,tract,field,acres,(dx,dy) in TASKS:
    data=INV['farms'][fid];v=next(v for v in source_views(SOURCE/data['candidate_fsa_pdf_sources'][0]['path']) if v[0]=='p1_c1')
    loc=data['spreadsheet_coordinate_hints'][0]
    image=get_tile(loc['longitude'],loc['latitude'],URL,dx,dy)
    if image is None:raise RuntimeError('NAIP tile unavailable for '+fid)
    reg=register(v,image)
    if not reg.get('nondegenerate_geographic_match_candidate'):
        raise RuntimeError('No stable homography for '+fid+': '+str(strip_result(reg)))
    x=R*math.radians(loc['longitude'])+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(loc['latitude'])/2))+dy*STEP
    record={'farm_id':fid,'tract_id':tract,'field_id':field,'printed_target_field_acres':acres,
      'source_pdf':data['candidate_fsa_pdf_sources'][0]['path'],
      'source_view':'p1_c1','source_view_size_wh':[v[1].shape[1],v[1].shape[0]],
      'target_tile_size_wh':[SIZE,SIZE],
      'tile_bbox_epsg3857':[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2],
      'homography_source_view_to_tile_px':reg['H'].tolist(),
      'registration_metrics':strip_result(reg),
      'status':'GEOREGISTRATION_CONFIRMED_FIELD_OUTLINE_UNDER_REVIEW'}
    (OUT/f'orangeburg_farm{fid}_field_registration_qc.json').write_text(json.dumps(record,indent=2)+'\n')
    cv2.imwrite(str(OUT/f'orangeburg_farm{fid}_source_view.jpg'),v[1],[cv2.IMWRITE_JPEG_QUALITY,91])
    cv2.imwrite(str(OUT/f'orangeburg_farm{fid}_independent_naip_view.jpg'),image,[cv2.IMWRITE_JPEG_QUALITY,91])
    mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),reg['H'],(SIZE,SIZE))
    warp=cv2.warpPerspective(v[1],reg['H'],(SIZE,SIZE))
    combo=cv2.addWeighted(image,.6,warp,.4,0);combo[mask==0]=image[mask==0]
    cv2.imwrite(str(OUT/f'orangeburg_farm{fid}_registration_overlay.jpg'),combo,[cv2.IMWRITE_JPEG_QUALITY,91])
    print('FARM',fid,'TRACT',tract,'FIELD',field,'INLIERS',reg['inliers'],flush=True)
