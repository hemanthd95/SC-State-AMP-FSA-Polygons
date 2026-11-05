"""Scanned FSA-to-aerial image registration pilot for Orangeburg, *diagnostics only*.

Never derive farm polygons or GPS from weak/degenerate matches. Source
coordinates are search hints. Four source-identified maps are evaluated first.
"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import io,json,math,os,time
import requests
import numpy as np,cv2,fitz

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'source-data/OneDrive_2026-11-03/SC State_AMP_FSA MAP'
INVENTORY=ROOT/'analysis/orangeburg_source_inventory.json'
OUT=ROOT/'analysis'
FARMS=os.getenv('ORANGEBURG_PILOT_FARMS','1271,1778,8242,13653').split(',')
DETECT=cv2.SIFT_create(nfeatures=2600,contrastThreshold=.008,edgeThreshold=18)
R=6378137.
SERVICES=[
 ('USGS_NAIP','https://imagery.nationalmap.gov/arcgis/rest/services/USGSNAIPImagery/ImageServer/exportImage'),
 ('Esri_World_Imagery','https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/export')
]
CROP_FRACS=[(.06,.08,.94,.76),(.03,.16,.97,.80)]
SIZE=850;SPAN=1650.;STEP=850.

def prepare(image):
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
    return cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8)).apply(gray)

def source_views(pdf):
    d=fitz.open(pdf)
    outputs=[]
    for j,page in enumerate(d):
        if j>=2:break
        scale=min(1.15,2800/max(page.rect.width,page.rect.height))
        pix=page.get_pixmap(matrix=fitz.Matrix(scale,scale),colorspace=fitz.csRGB,alpha=False)
        im=cv2.imdecode(np.frombuffer(pix.tobytes('png'),dtype=np.uint8),cv2.IMREAD_COLOR)
        if im is None:continue
        hh,ww=im.shape[:2]
        for k,(x0,y0,x1,y1) in enumerate(CROP_FRACS):
            crop=im[int(y0*hh):int(y1*hh),int(x0*ww):int(x1*ww)]
            h,w=crop.shape[:2]
            factor=min(1.,1100/max(h,w))
            if factor<1:crop=cv2.resize(crop,None,fx=factor,fy=factor)
            key,desc=DETECT.detectAndCompute(prepare(crop),None)
            if desc is not None and len(key)>100:
                outputs.append((f'p{j+1}_c{k+1}',crop,key,desc))
    d.close()
    return outputs

def get_tile(lon,lat,provider,dx,dy):
    x=R*math.radians(lon)+dx*STEP
    y=R*math.log(math.tan(math.pi/4+math.radians(lat)/2))+dy*STEP
    p={'bbox':','.join(f'{z:.3f}' for z in (x-SPAN/2,y-SPAN/2,x+SPAN/2,y+SPAN/2)),
       'bboxSR':'3857','imageSR':'3857','size':f'{SIZE},{SIZE}',
       'format':'jpg','f':'image'}
    try:
        res=requests.get(provider,params=p,timeout=35)
        res.raise_for_status()
        im=cv2.imdecode(np.frombuffer(res.content,dtype=np.uint8),cv2.IMREAD_COLOR)
        return im if im is not None and im.shape[:2]==(SIZE,SIZE) else None
    except Exception:return None

def register(view,img):
    key_src,desc_src=view[2],view[3]
    key_dst,desc_dst=DETECT.detectAndCompute(prepare(img),None)
    if desc_dst is None:return {'inliers':0,'reason':'no descriptors'}
    knn=cv2.FlannBasedMatcher(dict(algorithm=1,trees=5),dict(checks=48)).knnMatch(desc_src,desc_dst,k=2)
    good=[a for pair in knn if len(pair)==2 for a,b in [pair] if a.distance<.77*b.distance]
    if len(good)<8:return {'inliers':0,'matches':len(good)}
    src=np.float32([key_src[m.queryIdx].pt for m in good])
    dst=np.float32([key_dst[m.trainIdx].pt for m in good])
    H,mask=cv2.findHomography(src,dst,cv2.USAC_MAGSAC,4.0,maxIters=2500,confidence=.998)
    if H is None:return {'inliers':0,'matches':len(good)}
    keep=mask.ravel().astype(bool)
    inliers=int(keep.sum())
    if inliers<8:return {'inliers':inliers,'matches':len(good)}
    px=cv2.perspectiveTransform(src[:,None],H)[:,0]
    residual=float(np.sqrt(np.mean(np.sum((px[keep]-dst[keep])**2,axis=1))))
    h,w=view[1].shape[:2]
    corners=np.float32([[[.15*w,.15*h],[.85*w,.15*h],[.85*w,.85*h],[.15*w,.85*h]]])
    projected=cv2.perspectiveTransform(corners,H)[0]
    polygon_area=abs(cv2.contourArea(projected))
    spread_src=np.ptp(src[keep],axis=0)
    spread_dst=np.ptp(dst[keep],axis=0)
    plausible=(inliers>=24 and .0<residual<4
               and spread_src.min()>125 and spread_dst.min()>80
               and 1800<polygon_area<2200000)
    score=inliers*(1+min(float(spread_src.min()),600)/200)
    return {'inliers':inliers,'matches':len(good),'rmse_px':round(residual,2),
            'source_spread_px':np.round(spread_src,1).tolist(),
            'image_spread_px':np.round(spread_dst,1).tolist(),
            'projected_bbox_area_px':round(polygon_area,1),
            'nondegenerate_geographic_match_candidate':bool(plausible),
            'score':round(score,1),'good_matches':good,'inlier_mask':keep,
            'source_keypoints':key_src,'target_keypoints':key_dst,'H':H}

def strip_result(result):
    return {k:v for k,v in result.items() if k not in
            {'good_matches','inlier_mask','source_keypoints','target_keypoints','H'}}

def main():
    inventory=json.loads(INVENTORY.read_text())
    out=[]
    for fid in FARMS:
        record=inventory['farms'].get(fid)
        if not record or not record.get('candidate_fsa_pdf_sources'):
            print('SKIP no source',fid,flush=True);continue
        source=record['candidate_fsa_pdf_sources'][0]['path']
        points=record.get('spreadsheet_coordinate_hints') or []
        if not points:print('SKIP no location hint',fid,flush=True);continue
        lat=points[0]['latitude'];lon=points[0]['longitude']
        views=source_views(SOURCE/source)
        if not views:print('SKIP no keypoints',fid,flush=True);continue
        best=None
        tasks=[(name,url,dx,dy) for name,url in SERVICES
                for dx,dy in [(0,0),(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,-1)]]
        # Keep network bounded. A failed image lookup is never interpreted as
        # the farm being absent from the locality.
        print('START',fid,source,'views',len(views),'queries',len(tasks),flush=True)
        with ThreadPoolExecutor(max_workers=5) as pool:
            futs={pool.submit(get_tile,lon,lat,url,dx,dy):(name,dx,dy)
                  for name,url,dx,dy in tasks}
            for fut in as_completed(futs):
                name,dx,dy=futs[fut]
                try:im=fut.result()
                except Exception:im=None
                if im is None:continue
                for view in views:
                    data=register(view,im)
                    if 'score' not in data:continue
                    row={'farm_id':fid,'source_pdf':source,'source_view':view[0],
                        'imagery_provider':name,'tile_offset_dx_dy':[dx,dy],
                        'registration':strip_result(data)}
                    if best is None or (row['registration']['nondegenerate_geographic_match_candidate'],
                                        row['registration']['score'])>(best[0]['registration']['nondegenerate_geographic_match_candidate'],
                                                                         best[0]['registration']['score']):
                        best=(row,view,im,data)
        if best:
            item,view,im,check=best
            print('BEST',fid,item['imagery_provider'],
                  'inliers',check['inliers'],'area',check['projected_bbox_area_px'],
                  'plausible',check['nondegenerate_geographic_match_candidate'],flush=True)
            if check['nondegenerate_geographic_match_candidate']:
                retained=[m for i,m in enumerate(check['good_matches']) if check['inlier_mask'][i]]
                frame=cv2.drawMatches(view[1],view[2],im,check['target_keypoints'],retained[:100],None,
                                      flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
                frame=cv2.resize(frame,None,fx=.60,fy=.60)
                cv2.imwrite(str(OUT/f'orangeburg_pilot_match_farm_{fid}.jpg'),frame,[cv2.IMWRITE_JPEG_QUALITY,80])
            out.append(item)
        else:
            print('NO MATCH EVIDENCE',fid,flush=True)
            out.append({'farm_id':fid,'source_pdf':source,
                        'registration':{'nondegenerate_geographic_match_candidate':False,
                                        'reason':'no nonzero geometric registration'}})
    doc={'status':'REGISTRATION_DIAGNOSTICS_ONLY__NO_POLYGONS_ACCEPTED',
         'warning':'A high inlier count alone never verifies exact field geometry. Human review, source-field tracing and acreage checks are still required.',
         'farm_candidates':out}
    (OUT/'orangeburg_registration_pilot.json').write_text(json.dumps(doc,indent=2)+'\n')
    print('FINISHED',len(out),'diagnostic farms',flush=True)

if __name__=='__main__':main()
