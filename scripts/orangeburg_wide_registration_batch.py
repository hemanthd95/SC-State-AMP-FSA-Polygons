"""Bounded wider NAIP search for remaining identifiable Orangeburg FSA maps.

Search a roughly 12-km square around spreadsheet hints, return only high-quality
image homographies with review overlays. No polygons are invented or accepted.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import json, math, time
import cv2, numpy as np
from orangeburg_registration_pilot import SOURCE,OUT,SIZE,SPAN,STEP,R,source_views,get_tile,register,strip_result

TARGETS=[
    ('14187','Bruce Jenkins_FSA Map.pdf',[1,2],33.4213603,-80.6483627),
    ('14291','Edward Carson_FSA Map.pdf',[1],33.6101,-80.4521),
    ('13225','Morgan summers_FSA_Map.pdf',[1],33.3052023,-80.8244781),
    ('8242','Louie Johnson FSA_Map.pdf',[1],33.5068861,-80.8515095),
]
URL='https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'
# 49 tiles at >=1.7-km spacing, 1.65-km imagery each. A bounded search.
OFFSETS=[(x,y) for x in (-6,-4,-2,0,2,4,6) for y in (-6,-4,-2,0,2,4,6)]

def high_confidence(g):
    if not g.get('nondegenerate_geographic_match_candidate'):return False
    if g['inliers'] < 58 or g['rmse_px'] > 2.3:return False
    if min(g['source_spread_px'])<145 or min(g['image_spread_px'])<110:return False
    if g['projected_bbox_area_px']<5000:return False
    return True


def run_target(fid,pdf,pages,lat,lon):
    print('START',fid,pdf,flush=True)
    views=[v for v in source_views(SOURCE/pdf) if int(v[0].split('_')[0][1:]) in pages]
    if not views:return {'farm_id':fid,'status':'NO_SOURCE_VIEWS'}
    best=None
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs={pool.submit(get_tile,lon,lat,URL,dx,dy):(dx,dy) for dx,dy in OFFSETS}
        for fu in as_completed(futs):
            dx,dy=futs[fu]
            try:tile=fu.result()
            except Exception:tile=None
            if tile is None:continue
            for v in views:
                g=register(v,tile)
                if not high_confidence(g):continue
                if best is None or g['score']>best['reg']['score']:
                    best={'view':v,'tile':tile,'reg':g,'dx':dx,'dy':dy}
    if best is None:
        print('NO_CONFIDENT_MATCH',fid,flush=True)
        return {'farm_id':fid,'source_pdf':pdf,'status':'NO_HIGH_CONFIDENCE_MATCH_WITHIN_BOUNDED_RADIUS','searched_offsets':len(OFFSETS)}
    v=best['view'];tile=best['tile'];g=best['reg'];dx=best['dx'];dy=best['dy']
    x=R*math.radians(lon)+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*STEP
    box=[x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2]
    warp=cv2.warpPerspective(v[1],g['H'],(SIZE,SIZE))
    mask=cv2.warpPerspective(np.full(v[1].shape[:2],255,np.uint8),g['H'],(SIZE,SIZE))
    overlay=cv2.addWeighted(tile,.65,warp,.35,0)
    overlay[mask==0]=tile[mask==0]
    cv2.imwrite(str(OUT/f'orangeburg_wide_{fid}_source.jpg'),v[1])
    cv2.imwrite(str(OUT/f'orangeburg_wide_{fid}_satellite.jpg'),tile)
    cv2.imwrite(str(OUT/f'orangeburg_wide_{fid}_overlay.jpg'),overlay)
    print('FOUND',fid,v[0],'inliers',g['inliers'],'rmse',g['rmse_px'],flush=True)
    return {'farm_id':fid,'source_pdf':pdf,'status':'HIGH_CONFIDENCE_GEOMETRIC_CANDIDATE_NEEDS_FIELD_TRACE',
            'source_view':v[0],'source_view_size_wh':[v[1].shape[1],v[1].shape[0]],
            'offset_xy':[dx,dy],'tile_bbox_epsg3857':box,'tile_size_wh':[SIZE,SIZE],
            'homography_source_to_satellite':g['H'].tolist(),'registration':strip_result(g)}

def main():
    out=[]
    for target in TARGETS:
        out.append(run_target(*target))
    (OUT/'orangeburg_wide_registration_batch.json').write_text(json.dumps({
        'status':'DIAGNOSTICS_ONLY','results':out,
        'caution':'Never infer field boundaries from source-to-satellite matching alone.'},indent=2)+'\n')
    print('COMPLETE',len(out),'farm searches',flush=True)

if __name__=='__main__':main()
