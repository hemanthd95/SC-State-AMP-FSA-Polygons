"""Trace Jasper Summers Farm13653, Tract5515, FIELD1 only, not neighboring field or tract.

Manually traced yellow FSA interior ring. Cross-check printed 2.58 acres.
"""
import json,numpy as np,cv2
from pathlib import Path
from pyproj import Transformer,Geod
from shapely.geometry import Polygon,shape,mapping
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'analysis'
d=json.loads((A/'orangeburg_farm13653_tract5515_refinement.json').read_text())
assert d['status']=='REFINED_TARGET_FIELD_REGISTRATION_CANDIDATE'
assert d['registration_metrics']['inliers']>=100
assert d['tract_id']=='5515' and d['field_id']=='1'
# Only the labeled 2.58-acre interior field north of the road;
# excludes the unlabeled cap above and the long separate strip below.
src=np.float32([[295,81],[306,82],[322,87],[335,90],[297,242],[259,238]])
H=np.float64(d['homography_source_view_to_tile_px'])
tile=cv2.perspectiveTransform(src[None],H)[0]
x0,y0,x1,y1=d['tile_bbox_epsg3857'];w,h=d['target_tile_size_wh']
transform=Transformer.from_crs(3857,4326,always_xy=True)
pts=[transform.transform(x0+float(x)/w*(x1-x0),y1-float(y)/h*(y1-y0)) for x,y in tile]
poly=Polygon(pts)
if not poly.is_valid or poly.is_empty:raise RuntimeError('Invalid tract5515 field1 polygon')
acres=abs(Geod(ellps='WGS84').geometry_area_perimeter(poly)[0])/4046.8564224
err=abs(acres-2.58)/2.58*100
if err>6:raise RuntimeError(f'Printed acreage mismatch {acres:.3f} vs 2.58')
county=shape(json.loads((ROOT/'geojson/orangeburg_county_boundary.geojson').read_text())['features'][0]['geometry'])
if not county.buffer(1e-6).covers(poly):raise RuntimeError('Field outside official Orangeburg')
feature={'type':'Feature','geometry':mapping(poly),'properties':{
 'county':'Orangeburg','farm_id':'13653','tract_id':'5515','field_id':'1','producer':'Jasper Summers',
 'source_pdf':'Jasper Summers_FSA_Map.pdf','source_page':1,'fsa_printed_acres':2.58,
 'traced_geodesic_acres':round(acres,3),'area_difference_percent':round(err,2),
 'image_provider':'USGS NAIP Imagery',
 'registration_inliers':d['registration_metrics']['inliers'],
 'registration_rmse_pixels':d['registration_metrics']['rmse_px'],
 'registration_method':'SIFT and MAGSAC homography + human trace of printed FSA yellow interior field',
 'status':'CANDIDATE_UNDER_VISUAL_OVERLAY_QA',
 'note':'Excluded the other FSA tract5516 page and unlabeled portions of tract5515'}}
(A/'orangeburg_farm13653_tract5515_field1_candidate.geojson').write_text(json.dumps({
 'type':'FeatureCollection','features':[feature]},indent=2)+'\n')
for kind,path in [('source','orangeburg_farm13653_tract5515_refined_source.jpg'),
                  ('satellite','orangeburg_farm13653_tract5515_refined_overlay.jpg')]:
    im=cv2.imread(str(A/path))
    q=src if kind=='source' else tile
    cv2.polylines(im,[np.round(q).astype(np.int32)],True,(50,50,250),3,cv2.LINE_AA)
    for x,y in np.round(q).astype(np.int32):
        cv2.circle(im,(int(x),int(y)),4,(255,255,255),-1,cv2.LINE_AA)
    cv2.putText(im,f'TRACT 5515 FIELD 1: {acres:.2f}ac / FSA 2.58ac',
                (10,25),cv2.FONT_HERSHEY_SIMPLEX,.53,(250,250,250),2,cv2.LINE_AA)
    cv2.imwrite(str(A/f'orangeburg_farm13653_tract5515_field1_candidate_{kind}.jpg'),im,
                [cv2.IMWRITE_JPEG_QUALITY,93])
(A/'orangeburg_farm13653_tract5515_field1_qa.json').write_text(json.dumps({
 'farm_id':'13653','tract_id':'5515','field_id':'1','computed_acres':round(acres,3),
 'fsa_acres':2.58,'acreage_difference_pct':round(err,2),'county_check':'PASS',
 'registration_inliers':d['registration_metrics']['inliers'],
 'visual_review':'PENDING','source_pixel_vertices':src.tolist()},indent=2)+'\n')
print('JASPER 5515 FIELD1 candidate',round(acres,3),'acres; FSA 2.58',flush=True)
