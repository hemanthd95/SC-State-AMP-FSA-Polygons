"""Use system GDAL to extract only georeferenced imagery from an FSA GeoPDF."""
import argparse
import json
from pathlib import Path
from osgeo import gdal, ogr, osr

gdal.UseExceptions()
parser=argparse.ArgumentParser()
parser.add_argument('source',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--viewport',type=Path)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
ds=gdal.OpenEx(str(args.source),gdal.OF_RASTER,open_options=['RENDERING_OPTIONS=RASTER','DPI=200','BANDS=4'])
source_srs=ds.GetSpatialRef();source_srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
target=osr.SpatialReference();target.ImportFromEPSG(32617);target.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
if args.viewport:
    viewport=json.loads(args.viewport.read_text());x0,y0,x1,y1=viewport['bbox_page']
    gt=ds.GetGeoTransform();ring=ogr.Geometry(ogr.wkbLinearRing)
    for px,py in [(x0,y0),(x0,y1),(x1,y1),(x1,y0),(x0,y0)]:
        rx=px*ds.RasterXSize/viewport['page_width'];ry=py*ds.RasterYSize/viewport['page_height']
        ring.AddPoint(gt[0]+rx*gt[1]+ry*gt[2],gt[3]+rx*gt[4]+ry*gt[5])
    neatline=ogr.Geometry(ogr.wkbPolygon);neatline.AddGeometry(ring)
else:
    neatline=ogr.CreateGeometryFromWkt(ds.GetMetadataItem('NEATLINE'))
neatline.AssignSpatialReference(source_srs)
neatline.Transform(osr.CoordinateTransformation(source_srs,target))
xmin,xmax,ymin,ymax=neatline.GetEnvelope()
width=1800;height=round(width*(ymax-ymin)/(xmax-xmin))
tif=args.output/'imagery.tif'
warped=gdal.Warp(str(tif),ds,format='GTiff',dstSRS='EPSG:32617',
                outputBounds=[xmin,ymin,xmax,ymax],width=width,height=height,
                resampleAlg='bilinear',dstAlpha=True,creationOptions=['COMPRESS=DEFLATE'])
assert warped is not None
gdal.Translate(str(args.output/'imagery.png'),warped,format='PNG',bandList=[1,2,3,4])
(args.output/'imagery_reference.json').write_text(json.dumps({
    'crs':'EPSG:32617','bounds':[xmin,ymin,xmax,ymax],
    'width':width,'height':height,'rendered_components':'RASTER ONLY',
    'source':args.source.name,'source_neatline_wkt':ds.GetMetadataItem('NEATLINE'),
},indent=2))
print(args.source.name,'imagery only:',width,height)
