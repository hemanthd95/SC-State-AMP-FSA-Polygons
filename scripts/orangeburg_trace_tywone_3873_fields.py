"""Test exact FSA-photo Field1 and Field4 traces for Tywone Farm3873.

Candidates only. Verify outlines visually against the original source and USGS
NAIP before merging the GeoJSON or re-rendering the county atlases.
"""
import json,cv2,numpy as np
from pathlib import Path
from shapely.geometry import Polygon,shape,mapping
from pyproj import Transformer,Geod

ROOT=Path(__file__).resolve().parents[1];A=ROOT/'analysis'
r=json.loads((A/'orangeburg_farm3873_complete_field_registration.json').read_text())
assert r['farm_id']=='3873' and r['tract_id']=='3895' and r['source_page']==1
assert r['metrics']['nondegenerate_geographic_match_candidate'] and r['metrics']['inliers']>=100
H=np.array(r['homography_source_view_to_target_px'],dtype=np.float64)
x0,y0,x1,y1=r['target_bbox_epsg3857'];w,h=r['image_size_wh']
toLL=Transformer.from_crs(3857,4326,always_xy=True)
county=shape(json.loads((ROOT/'geojson/orangeburg_county_boundary.geojson').read_text())['features'][0]['geometry'])
source=cv2.imread(str(A/'orangeburg_farm3873_complete_source.jpg'))
sat=cv2.imread(str(A/'orangeburg_farm3873_complete_naip.jpg'))
if source is None or sat is None:raise RuntimeError('Missing review photos')
fields={
 '1':{'fsa_acres':.43,'points':[(355,304),(362,288),(370,276),(381,269),(387,267),(389,264),(392,295)]},
 '4':{'fsa_acres':1.93,'points':[(391,263),(401,247),(423,241),(444,240),(461,246),(461,286),(395,298)]},
}
features=[];qc=[]
for fid,d in fields.items():
    src=np.float32(d['points'])
    pix=cv2.perspectiveTransform(src[None],H)[0]
    assert np.all((pix[:,0]>2)&(pix[:,0]<w-2)&(pix[:,1]>2)&(pix[:,1]<h-2))
    ring=[]
    for u,v in pix:
        lon,lat=toLL.transform(x0+float(u)*(x1-x0)/w,y1-float(v)*(y1-y0)/h)
        ring.append((lon,lat))
    poly=Polygon(ring)
    if not poly.is_valid or poly.is_empty:raise RuntimeError('Invalid polygon Field'+fid)
    if not county.buffer(1e-5).covers(poly):raise RuntimeError('Outside Orangeburg County Field'+fid)
    acres=abs(Geod(ellps='WGS84').geometry_area_perimeter(poly)[0])/4046.8564224
    err=100*abs(acres-d['fsa_acres'])/d['fsa_acres']
    if err>=12:raise RuntimeError(f'Field{fid} FSA area disagrees: {acres:.3f} vs {d["fsa_acres"]:.3f}, {err:.1f}%')
    p={'county':'Orangeburg','farm_id':'3873','tract_id':'3895','field_id':fid,
       'producer':'Tywone Hillard','source_pdf':r['source_pdf'],'source_page':1,
       'fsa_printed_acres':d['fsa_acres'],'traced_geodesic_acres':round(acres,3),
       'area_difference_percent':round(err,2),'image_provider':'USGS NAIP Imagery',
       'registration_inliers':r['metrics']['inliers'],'registration_rmse_pixels':r['metrics']['rmse_px'],
       'registration_method':'Verified FSA aerial photograph homography; source field line hand-traced',
       'status':'CANDIDATE_UNDER_VISUAL_OVERLAY_QA'}
    features.append({'type':'Feature','properties':p,'geometry':mapping(poly)})
    qc.append({'field_id':fid,'source_acres':d['fsa_acres'],'traced_acres':round(acres,3),
               'difference_percent':round(err,2),'spatial_registration':'PASS','county':'PASS',
               'visual_boundary_check':'PENDING'})
    for kind,img,pp in [('source',source,src),('satellite',sat,pix)]:
        pts=np.rint(pp).astype(np.int32)
        cv2.polylines(img,[pts],True,(25,65,250),3,cv2.LINE_AA)
        cv2.putText(img,f'F{fid}',tuple(pts[0]),cv2.FONT_HERSHEY_SIMPLEX,.65,(255,255,255),2,cv2.LINE_AA)
    print('TRACE CANDIDATE',fid,round(acres,3),'ac vs FSA',d['fsa_acres'],'err',round(err,2),flush=True)
(A/'orangeburg_farm3873_field1_field4_candidate.geojson').write_text(json.dumps({'type':'FeatureCollection','features':features},indent=2)+'\n')
(A/'orangeburg_farm3873_field1_field4_candidate_qa.json').write_text(json.dumps(qc,indent=2)+'\n')
cv2.imwrite(str(A/'orangeburg_farm3873_fields_candidate_source.jpg'),source)
cv2.imwrite(str(A/'orangeburg_farm3873_fields_candidate_satellite.jpg'),sat)
crop=source[205:335,305:490]
cv2.imwrite(str(A/'orangeburg_farm3873_fields_candidate_source_zoom.jpg'),
            cv2.resize(crop,None,fx=5,fy=5,interpolation=cv2.INTER_CUBIC))
