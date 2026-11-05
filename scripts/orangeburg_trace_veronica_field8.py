"""Digitize exactly the FSA Field8 polygon from alternate Veronica PDF page20.

The white/yellow interior field boundary excludes the surrounding wooded tract,
the adjacent Field17, and all unrelated alternate-PDF pages.
"""
import json,cv2,numpy as np
from pathlib import Path
from pyproj import Transformer,Geod
from shapely.geometry import Polygon,shape,mapping
ROOT=Path(__file__).resolve().parents[1];A=ROOT/'analysis'
r=json.loads((A/'orangeburg_veronica_45514_field8_georegistration.json').read_text())
assert (r['farm_id'],r['tract_id'],r['field_id'],r['source_page'])==('13709','45514','8',20)
assert r['registration']['nondegenerate_geographic_match_candidate'] and r['registration']['inliers']>70
H=np.array(r['H_source_to_tile'],dtype=float)
x0,y0,x1,y1=r['bbox_epsg3857'];w,h=r['target_tile_size_wh']
src=np.float32([[168,155],[188,180],[224,222],[265,244],[322,256],
 [368,268],[339,310],[325,344],[312,369],[311,405],[302,430],
 [260,470],[217,486],[143,505],[34,495]])
tile=cv2.perspectiveTransform(src[None],H)[0]
toLL=Transformer.from_crs(3857,4326,always_xy=True)
poly=Polygon([toLL.transform(x0+float(u)*(x1-x0)/w,
                             y1-float(v)*(y1-y0)/h) for u,v in tile])
if not poly.is_valid or poly.is_empty:raise RuntimeError('Invalid Field8 geometry')
county=shape(json.loads((ROOT/'geojson/orangeburg_county_boundary.geojson').read_text())['features'][0]['geometry'])
if not county.buffer(1e-6).covers(poly):raise RuntimeError('Field8 outside county')
acres=abs(Geod(ellps='WGS84').geometry_area_perimeter(poly)[0])/4046.8564224
pct=100*abs(acres-4.79)/4.79
if pct>6:raise RuntimeError(f'FSA Field8 acreage mismatch: {acres:.3f}, error{pct:.1f}%')
props={'county':'Orangeburg','farm_id':'13709','tract_id':'45514',
 'field_id':'8','producer':'Veronica Hodges',
 'source_pdf':r['source_pdf'],'source_page':20,'fsa_printed_acres':4.79,
 'traced_geodesic_acres':round(acres,3),'area_difference_percent':round(pct,2),
 'image_provider':'USGS NAIP Imagery','registration_inliers':r['registration']['inliers'],
 'registration_rmse_pixels':r['registration']['rmse_px'],
 'registration_method':'SIFT aerial homography; exact bright-yellow FSA Field8 boundary hand-traced',
 'status':'CANDIDATE_UNDER_VISUAL_OVERLAY_QA'}
data={'type':'FeatureCollection','features':[{'type':'Feature','geometry':mapping(poly),'properties':props}]}
(A/'orangeburg_veronica_field8_candidate.geojson').write_text(json.dumps(data,indent=2)+'\n')
for kind,path,pts in [
 ('source',A/'orangeburg_veronica_field8_source_view.jpg',src),
 ('satellite',A/'orangeburg_veronica_field8_naip_view.jpg',tile)]:
    im=cv2.imread(str(path));assert im is not None
    coords=np.rint(pts).astype(np.int32)
    cv2.polylines(im,[coords],True,(20,70,245),3,cv2.LINE_AA)
    cv2.putText(im,f'T45514 F8 / {acres:.2f}ac', (8,22),
        cv2.FONT_HERSHEY_SIMPLEX,.6,(255,255,255),2,cv2.LINE_AA)
    cv2.imwrite(str(A/f'orangeburg_veronica_field8_candidate_{kind}.jpg'),im)
(A/'orangeburg_veronica_field8_candidate_qa.json').write_text(json.dumps({
 'farm_id':'13709','tract_id':'45514','field_id':'8','printed_acres':4.79,
 'measured_acres':round(acres,3),'difference_percent':round(pct,2),
 'county':'PASS','image_registration':'PASS','visual_trace':'PENDING'},indent=2)+'\n')
print('VERONICA FIELD8',round(acres,3),'acres versus 4.79 FSA',round(pct,2),'percent discrepancy',flush=True)
