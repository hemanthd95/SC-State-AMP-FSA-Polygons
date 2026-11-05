"""Refine Farm3873/Tract3895 original-page FSA alignment, with complete field coverage."""
import json,math
import cv2,numpy as np
from orangeburg_registration_pilot import ROOT,SOURCE,OUT,R,SPAN,STEP,SIZE,source_views,get_tile,register,strip_result
inv=json.loads((OUT/'orangeburg_source_inventory.json').read_text())
m=inv['farms']['3873']
source=m['candidate_fsa_pdf_sources'][0]['path']
loc=m['spreadsheet_coordinate_hints'][0]
views=[v for v in source_views(SOURCE/source) if v[0].startswith('p1_')]
url='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
best=None;tests=[]
for dx,dy in [(3,0),(3,1),(3,-1),(2,0),(2,1),(4,0)]:
  im=get_tile(loc['longitude'],loc['latitude'],url,dx,dy)
  if im is None:continue
  for v in views:
    g=register(v,im)
    tests.append({'source_view':v[0],'offset':[dx,dy],'metrics':strip_result(g)})
    if g.get('nondegenerate_geographic_match_candidate') and (best is None or g['score']>best['reg']['score']):
      best={'view':v,'image':im,'reg':g,'dx':dx,'dy':dy}
if best is None:raise RuntimeError('No nondegenerate georegistration found for requested farm map')
v=best['view'];im=best['image'];g=best['reg'];dx=best['dx'];dy=best['dy']
x=R*math.radians(loc['longitude'])+dx*STEP
y=R*math.log(math.tan(math.pi/4+math.radians(loc['latitude'])/2))+dy*STEP
bbox=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
pts=np.float32([[340,240],[470,240],[470,330],[340,330]])
proj=cv2.perspectiveTransform(pts[None],g['H'])[0]
if not np.all((proj[:,0]>50)&(proj[:,0]<SIZE-50)&(proj[:,1]>50)&(proj[:,1]<SIZE-50)):
    raise RuntimeError('FSA target fields still cropped out of NAIP tile: '+str(proj.tolist()))
out={'farm_id':'3873','tract_id':'3895','field_ids':['1','4'],
 'source_pdf':source,'source_page':1,'source_view':v[0],
 'target_bbox_epsg3857':bbox,'image_size_wh':[SIZE,SIZE],
 'view_size_wh':[v[1].shape[1],v[1].shape[0]],
 'homography_source_view_to_target_px':g['H'].tolist(),
 'metrics':strip_result(g),'target_field_region_tile_bbox_xyxy':[float(proj[:,0].min()),float(proj[:,1].min()),float(proj[:,0].max()),float(proj[:,1].max())],
 'status':'REGISTRATION_AND_FIELD_REGION_IN_TILE_QA_PASS__POLYGON_TRACING_PENDING',
 'tests':tests}
(OUT/'orangeburg_farm3873_complete_field_registration.json').write_text(json.dumps(out,indent=2)+'\n')
cv2.imwrite(str(OUT/'orangeburg_farm3873_complete_source.jpg'),v[1])
cv2.imwrite(str(OUT/'orangeburg_farm3873_complete_naip.jpg'),im)
warped=cv2.warpPerspective(v[1],g['H'],(SIZE,SIZE))
mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),g['H'],(SIZE,SIZE))
mix=cv2.addWeighted(im,.64,warped,.36,0);mix[mask==0]=im[mask==0]
cv2.imwrite(str(OUT/'orangeburg_farm3873_complete_overlay.jpg'),mix)
print('FARM3873 target-page: ',v[0],dx,dy,'inliers',g['inliers'],'RMSE',g['rmse_px'],'field region',out['target_field_region_tile_bbox_xyxy'],flush=True)
