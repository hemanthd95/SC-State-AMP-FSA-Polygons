# SC State AMP / FSA field polygon extraction

This folder contains georeferenced field polygons extracted from FSA-produced GeoPDF vector map pages supplied in `OneDrive_2026-11-03.zip`.

**Data status (November 3, 2026):** 22 labeled field polygons from 6 distinct FSA PDF maps in 5 South Carolina counties. The source ZIP has 110 PDFs; only geospatial vector-boundary maps with a matched printed field identifier and acreage were admitted.

| County | Admitted field polygons |
| --- | ---: |
| Barnwell | 4 |
| Darlington | 4 |
| Florence | 1 |
| Marion | 4 |
| Williamsburg | 9 |
| **Total** | **22** |

## Download and use

1. Download `geojson/master_fsa_fields_geopdf_verified.geojson` for all admitted polygons, or a county-specific file from `geojson/counties/`. Sign in to GitHub; this repository is private.
2. In QGIS, use **Layer > Add Layer > Add Vector Layer**, select the GeoJSON, and confirm the layer uses **EPSG:4326 (WGS 84)**. GeoJSON coordinates are longitude, latitude.
3. Style by `farm_id` (categorical) or `county`; use `field_id` as a label. The attributes retain `tract_id`, printed FSA acreage, independently calculated approximate polygon acreage, source PDF filename, and SHA-256.
4. Check `qa/extracted_field_manifest.csv` for area comparisons and `qa/pdf_source_inventory.csv` for maps not yet admitted.

## Method and data quality

- Source: geospatial PDF viewport (/Measure /GEO with /GPTS and /LPTS) and visible colored vector CLU field outlines.
- Each selected outline was matched to the corresponding printed FSA **field number and acreage**; closed coordinates were transformed to WGS84, checked for ring self-crossing and South Carolina geographic extent, and checked against printed area.
- Largest absolute difference between polygon-derived and printed FSA field acreage: **0.95%**. Maximum affine corner-fit residual in the admitted PDFs: **0.28 m**. These are internal QA diagnostics, **not estimates of absolute positional accuracy**.
- Field polygons are administrative FSA map interpretations, **not legal surveys or ownership boundaries**.
- The `geometry_status` attribute explicitly preserves the current verification level. Additional visual overlay and field/site verification are recommended before decisions involving actual property boundaries.
- No crop type has been inferred from imagery.
- Individual scanned/photographed maps and non-georeferenced PDFs are **not** represented by invented buffers or point-derived polygons.
- Producer phone numbers, emails and mailing addresses from the spreadsheets were intentionally excluded. Farm/tract/field IDs and PDF source names remain identifiable and the repository must stay private.

## Coverage still requiring work

- 99 PDF files need individual map-type review and/or image-based georeferencing.
- 4 existing county output maps were not treated as source polygons.
- 1 duplicate georeferenced PDF was not double-counted.

The source inventory is **file-based**, not a unique-farmer count. Several PDFs may be duplicate versions, contain multiple pages, or be administrative records rather than field maps.

## File structure

- `geojson/master_fsa_fields_geopdf_verified.geojson` - all admitted field polygons
- `geojson/counties/*.geojson` - county-level subsets
- `qa/extracted_field_manifest.csv` - feature-level geometry/acreage checks
- `qa/pdf_source_inventory.csv` - source PDF disposition

For the remaining FSA scans, first identify reliable ground-control points or a georeferenced source image, georeference each map, trace the field outline, and compare area and location against the source. Keep tentative digitizations in a separate review layer.
