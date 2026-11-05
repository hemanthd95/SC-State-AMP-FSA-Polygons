"""Trace Tarsha Mosley FSA field1 after independent aerial registration.

Property outline follows the source image yellow diamond, not parcel guesses.
"""
import json,numpy as np,cv2
from pathlib import Path
from pyproj import Transformer,Geod
from shapely.geometry import Polygon,shape,mapping
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'analysis'
d=json.loads((A/'orangeburg_farm14048_field_registration_qc.json').read_text())
assert d['farm_id']=='14048' and d['tract_id']=='46008' and d['field_id']=='1'
assert d['registration_metrics']['nondegenerate_geographic_match_candidate']
assert d['registration_metrics']['inliers']>=60
src=np.float32([[289,241],[385,324],[321,381],[227,294]])
H=np.array(d['homography_source_view_to_tile_px'],dtype=np.float64)
tile=cv2.perspectiveTransform(src[None],H)[0]
x0,y0,x1,y1=d['tile_bbox_epsg3857'];w,h=d['target_tile_size_wh']
to4326=Transformer.from_crs(3857,4326,always_xy=True)
poly=Polygon([to4326.transform(x0+float(x)/w*(x1-x0),
                                  y1-float(y)/h*(y1-y0)) for x,y in tile])
if not poly.is_valid or poly.is_empty:raise RuntimeError('Invalid farm14048 geometry')
acres=abs(Geod(ellps='WGS84').geometry_area_perimeter(poly)[0])/4046.8564224
err=abs(acres-.89)/.89*100
if err>=6:raise RuntimeError(f'FSA 0.89ac area mismatch: measured {acres:.3f}')
county=shape(json.loads((ROOT/'geojson/orangeburg_county_boundary.geojson').read_text())['features'][0]['geometry'])
if not county.buffer(1e-6).covers(poly):raise RuntimeError('Field outside county')
feature={'type':'Feature','geometry':mapping(poly),'properties':{
 'county':'Orangeburg','farm_id':'14048','tract_id':'46008','field_id':'1',
 'producer':'Tarsha Mosley','source_pdf':d['source_pdf'],'source_page':1,
 'fsa_printed_acres':.89,'traced_geodesic_acres':round(acres,3),
 'area_difference_percent':round(err,2),'image_provider':'USGS NAIP Imagery',
 'registration_inliers':d['registration_metrics']['inliers'],
 'registration_rmse_pixels':d['registration_metrics']['rmse_px'],
 'registration_method':'SIFT homography and manually digitized FSA yellow field boundary',
 'status':'CANDIDATE_UNDER_VISUAL_OVERLAY_QA'}}
(A/'orangeburg_farm14048_field1_candidate.geojson').write_text(json.dumps({'type':'FeatureCollection','features':[feature]},indent=2)+'\n')
for kind,p in [('source','orangeburg_farm14048_source_view.jpg'),
               ('satellite','orangeburg_farm14048_independent_naip_view.jpg')]:
    im=cv2.imread(str(A/p));pts=np.rint(src if kind=='source' else tile).astype(np.int32)
    cv2.polylines(im,[pts],True,(40,55,245),3,cv2.LINE_AA)
    for x,y in pts:cv2.circle(im,(int(x),int(y)),4,(255,255,255),-1,cv2.LINE_AA)
    cv2.putText(im,f'FSA FIELD1 {acres:.2f} ac / 0.89 FSA',(10,28),
                cv2.FONT_HERSHEY_SIMPLEX,.57,(255,255,255),2,cv2.LINE_AA)
    cv2.imwrite(str(A/f'orangeburg_farm14048_field1_candidate_{kind}.jpg'),im,[cv2.IMWRITE_JPEG_QUALITY,93])
(A/'orangeburg_farm14048_field1_candidate_qa.json').write_text(json.dumps({
  'farm_id':'14048','tract_id':'46008','field_id':'1','fsa_acres':.89,
  'measured_acres':round(acres,3),'difference_percent':round(err,2),
  'county_check':'PASS','status':'PENDING_VISUAL_REVIEW'},indent=2)+'\n')
print('TARSHA FARM14048 FIELD1',round(acres,3),'acres',flush=True)
