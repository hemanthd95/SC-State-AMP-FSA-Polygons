"""Check Montez Hillard Farm1033 source Field4 against nearby known-good Tywone imagery.

Shared highway-loop landmarks are useful, but only a nondegenerate, high-feature
image registration warrants actual georeferencing. No polygon accepted here.
"""
import json,math
from pathlib import Path
import cv2,numpy as np
from orangeburg_registration_pilot import SOURCE,OUT,source_views,register,get_tile,strip_result,R,STEP,SPAN,SIZE
fid='1033';inv=json.loads((OUT/'orangeburg_source_inventory.json').read_text());meta=inv['farms'][fid]
source=meta['candidate_fsa_pdf_sources'][0]['path']
loc=meta['spreadsheet_coordinate_hints'][0]
views=[v for v in source_views(SOURCE/source) if v[0].startswith('p1_')]
known=json.loads((OUT/'orangeburg_farm3873_complete_field_registration.json').read_text())
img=cv2.imread(str(OUT/'orangeburg_farm3873_complete_naip.jpg'))
if img is None:raise RuntimeError('Known valid nearby NAIP unavailable')
candidates=[('Nearby_Farm3873_USGS_NAIP',img,known['target_bbox_epsg3857'])]
url='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
for dx,dy in [(3,0),(4,-1),(4,0),(2,-1),(3,1),(2,1),(4,1)]:
    tile=get_tile(loc['longitude'],loc['latitude'],url,dx,dy)
    if tile is None:continue
    x=R*math.radians(loc['longitude'])+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(loc['latitude'])/2))+dy*STEP
    candidates.append((f'USGS_NAIP_offset_{dx}_{dy}',tile,[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]))
best=None;tests=[]
for name,image,bounds in candidates:
    for v in views:
        g=register(v,image)
        tests.append({'tile':name,'view':v[0],'metrics':strip_result(g)})
        if not g.get('nondegenerate_geographic_match_candidate'):continue
        if best is None or g['score']>best['result']['score']:
            best={'tile':name,'image':image,'bounds':bounds,'view':v,'result':g}
report={'farm_id':fid,'tract_id':'3879','field_id':'4','source_pdf':source,'source_page':1,
        'status':'NO_DEFINITIVE_ALIGNMENT','tests':tests}
if best:
    name,im,bbox,v,g=best['tile'],best['image'],best['bounds'],best['view'],best['result']
    report.update(status='MATCH_CANDIDATE_SOURCE_FIELD_TRACE_REQUIRED',tile_source=name,
        tile_bbox_epsg3857=bbox,tile_size_wh=[SIZE,SIZE],source_view=v[0],
        source_view_size_wh=[v[1].shape[1],v[1].shape[0]],
        homography_source_to_tile_px=g['H'].tolist(),metrics=strip_result(g))
    cv2.imwrite(str(OUT/'orangeburg_montez_farm1033_match_source.jpg'),v[1])
    cv2.imwrite(str(OUT/'orangeburg_montez_farm1033_match_naip.jpg'),im)
    warp=cv2.warpPerspective(v[1],g['H'],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),g['H'],(SIZE,SIZE))
    overlay=cv2.addWeighted(im,.65,warp,.35,0);overlay[mask==0]=im[mask==0]
    cv2.imwrite(str(OUT/'orangeburg_montez_farm1033_match_overlay.jpg'),overlay)
    print('VALID SHARED-LOCATION HOMOGRAPHY',name,v[0],g['inliers'],'inliers',g['rmse_px'],'px RMSE',flush=True)
else:
    print('NOT LOCATED: no safe Montez Farm1033 homography near shared highway interchange',flush=True)
(OUT/'orangeburg_montez_farm1033_georegistration.json').write_text(json.dumps(report,indent=2)+'\n')
