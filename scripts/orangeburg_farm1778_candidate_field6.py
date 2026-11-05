"""Trace FSA field 6 of Orangeburg Farm 1778 after verified image registration.

Hand-traced vertices are measured in the registered FSA screenshot's own
pixel grid. Print-acreage and official county containment must both pass.
Output remains a REVIEW CANDIDATE until overlay is visually checked.
"""
import json
from pathlib import Path
import numpy as np,cv2
from pyproj import Transformer,Geod
from shapely.geometry import Polygon,shape,mapping

ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'analysis'
G=ROOT/'geojson/orangeburg_county_boundary.geojson'
D=json.loads((A/'orangeburg_farm1778_registration_qc.json').read_text())
assert D['farm_id']=='1778' and D['tract_id']=='1334' and D['target_field_id']=='6'
assert D['registration_metrics']['inliers']>=60
assert D['registration_metrics']['nondegenerate_geographic_match_candidate']
# Source-image pixels, manually traced from the exact printed yellow boundary.
# Nodes clockwise: northwest corner, northeast, east, boundary notch, south,
# and southwest field-side boundary. This is Field 6, not its parent tract.
source_xy=np.array([
    [363,163],[507,90],[507,154],[466,183],[466,211],
    [416,245],[387,201]
],dtype=np.float32)
H=np.array(D['homography_source_view_to_tile_px'],dtype=np.float64)
tile_xy=cv2.perspectiveTransform(source_xy[None],H)[0]
x0,y0,x1,y1=D['tile_bbox_epsg3857']
tw,th=D['target_tile_size_wh']
merc=[(x0+(x/tw)*(x1-x0),y1-(y/th)*(y1-y0)) for x,y in tile_xy]
to4326=Transformer.from_crs(3857,4326,always_xy=True)
points=[to4326.transform(x,y) for x,y in merc]
poly=Polygon(points)
if not poly.is_valid or poly.is_empty:raise ValueError('Invalid field-6 digitization')
geod=Geod(ellps='WGS84')
area_sq_m=abs(geod.geometry_area_perimeter(poly)[0])
acres=area_sq_m/4046.8564224
reported=D['printed_target_field_acres']
error_pct=100*abs(acres-reported)/reported
if error_pct>=6:raise ValueError(f'FSA boundary acreage check failed: {acres:.3f} vs {reported}')
county=json.loads(G.read_text())['features'][0]
county_shape=shape(county['geometry'])
if not county_shape.buffer(1e-6).covers(poly):
    raise ValueError('Candidate field polygon falls outside official Orangeburg County')
record={'type':'Feature','geometry':mapping(poly),'properties':{
    'county':'Orangeburg','farm_id':'1778','tract_id':'1334','field_id':'6',
    'producer':'Robert Seaberry','source_pdf':'Robert Seaberry Jr. FSA.pdf',
    'source_page':1,'fsa_printed_acres':reported,
    'traced_geodesic_acres':round(acres,3),
    'area_difference_percent':round(error_pct,2),
    'image_provider':'USGS NAIP Imagery',
    'registration_inliers':D['registration_metrics']['inliers'],
    'registration_rmse_pixels':D['registration_metrics']['rmse_px'],
    'registration_method':'SIFT and MAGSAC homography + human trace of printed FSA yellow field boundary',
    'status':'CANDIDATE_UNDER_VISUAL_OVERLAY_QA'}} 
dest=A/'orangeburg_farm1778_field6_candidate.geojson'
dest.write_text(json.dumps({'type':'FeatureCollection','features':[record]},indent=2)+'\n')
# Draw candidate on both maps to compare against printed FSA yellow boundary.
src=cv2.imread(str(A/'orangeburg_farm1778_source_registration_view.jpg'))
aerial=cv2.imread(str(A/'orangeburg_farm1778_satellite_registration_view.jpg'))
for name,im,pts in [('source',src,source_xy),('satellite',aerial,tile_xy)]:
    ptsi=np.round(pts).astype(np.int32)
    cv2.polylines(im,[ptsi],True,(45,60,255),3,cv2.LINE_AA)
    for j,(x,y) in enumerate(ptsi):
        cv2.circle(im,(int(x),int(y)),5,(250,250,250),-1,cv2.LINE_AA)
        cv2.circle(im,(int(x),int(y)),3,(20,65,255),-1,cv2.LINE_AA)
    cv2.putText(im,f'FIELD 6 candidate: {acres:.2f} ac / FSA {reported:.2f} ac',
                (12,30),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),2,cv2.LINE_AA)
    cv2.imwrite(str(A/f'orangeburg_farm1778_field6_candidate_{name}.jpg'),im,[cv2.IMWRITE_JPEG_QUALITY,94])
(A/'orangeburg_farm1778_field6_candidate_qa.json').write_text(json.dumps({
    'farm_id':'1778','tract_id':'1334','field_id':'6',
    'geodesic_acres':round(acres,3),'fsa_acres':reported,
    'area_difference_pct':round(error_pct,2),
    'within_official_orangeburg_county':True,
    'registration_inliers':D['registration_metrics']['inliers'],
    'registration_rmse_px':D['registration_metrics']['rmse_px'],
    'source_pixel_vertices':source_xy.tolist(),
    'target_tile_vertices':tile_xy.tolist(),
    'status':'PENDING_HUMAN_VISUAL_QA'} ,indent=2)+'\n')
print('FSA FIELD6 CANDIDATE acres',round(acres,3),'error_pct',round(error_pct,2),flush=True)
