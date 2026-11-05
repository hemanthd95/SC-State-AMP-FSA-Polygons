"""Register exact Farm13709/Tract45514/Field8 from alternate 21-page FSA PDF.

The FSA map's printed 4.79-ac Field8 boundary is separate from adjacent
Field17 and the full tract. Candidate alignment only until field trace QA.
"""
import json,math
from concurrent.futures import ThreadPoolExecutor,as_completed
import cv2,numpy as np
from orangeburg_registration_pilot import OUT,DETECT,prepare,register,get_tile,strip_result,R,SIZE,SPAN,STEP
im=cv2.imread(str(OUT/'orangeburg_veronica_alt21_match_page20.jpg'))
if im is None:raise RuntimeError('FSA page20 scan unavailable')
crop=im[44:739,15:710]
keys,desc=DETECT.detectAndCompute(prepare(crop),None)
if desc is None or len(keys)<100:raise RuntimeError('Insufficient FSA source features')
view=('p20_tract45514',crop,keys,desc)
inventory=json.loads((OUT/'orangeburg_source_inventory.json').read_text())
locs=inventory['farms']['13709']['spreadsheet_coordinate_hints']
url='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
jobs=[]
for k,p in enumerate(locs):
    for dx,dy in [(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1),(1,-1),(-1,1),(2,0),(-2,0)]:
        jobs.append((k,p['longitude'],p['latitude'],dx,dy))
best=None;report=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    future={pool.submit(get_tile,lon,lat,url,dx,dy):(k,lon,lat,dx,dy) for k,lon,lat,dx,dy in jobs}
    for fut in as_completed(future):
        k,lon,lat,dx,dy=future[fut]
        try:img=fut.result()
        except Exception:img=None
        if img is None:continue
        g=register(view,img)
        if g.get('nondegenerate_geographic_match_candidate'):
            report.append({'hint_index':k,'offset':[dx,dy],'registration':strip_result(g)})
            if best is None or g['score']>best['registration']['score']:
                best={'image':img,'registration':g,'location':[lon,lat],'dx':dx,'dy':dy,'hint_index':k}
d={'farm_id':'13709','tract_id':'45514','field_id':'8','source_pdf':'Vronica Hodges_FSA_Map.pdf',
   'source_page':20,'fsa_printed_acres':4.79,
   'image_source_crop_xyxy':[15,44,710,739],'search_match_candidates':report,
   'status':'NO_STABLE_GEOREGISTRATION__NOT_ACCEPTED'}
if best:
    g=best['registration'];lon,lat=best['location'];dx=best['dx'];dy=best['dy']
    x=R*math.radians(lon)+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*STEP
    d.update(status='STABLE_GEOREGISTRATION_CANDIDATE_FIELD_TRACE_PENDING',
      hint_index=best['hint_index'],offset_dx_dy=[dx,dy],
      source_view_size_wh=[crop.shape[1],crop.shape[0]],target_tile_size_wh=[SIZE,SIZE],
      bbox_epsg3857=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2],
      H_source_to_tile=g['H'].tolist(),registration=strip_result(g))
    cv2.imwrite(str(OUT/'orangeburg_veronica_field8_source_view.jpg'),crop)
    cv2.imwrite(str(OUT/'orangeburg_veronica_field8_naip_view.jpg'),best['image'])
    warp=cv2.warpPerspective(crop,g['H'],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.full(crop.shape[:2],255,np.uint8),g['H'],(SIZE,SIZE))
    combo=cv2.addWeighted(best['image'],.65,warp,.35,0);combo[mask==0]=best['image'][mask==0]
    cv2.imwrite(str(OUT/'orangeburg_veronica_field8_registration_overlay.jpg'),combo)
    print('FSA Tract45514 Field8 located',g['inliers'],'inliers',g['rmse_px'],'px',flush=True)
else:
    print('Exact requested Field8 source page not yet matched to independent NAIP',flush=True)
(OUT/'orangeburg_veronica_45514_field8_georegistration.json').write_text(json.dumps(d,indent=2)+'\n')
