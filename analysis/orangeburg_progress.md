# Orangeburg County AMP/FSA field atlas — verification ledger

*Updated 2026-11-05. Private project information.*

## Scope
- 18 farm IDs in source workbook, 17 in this delivery batch.
- Farm 14043 (Mary Koon) **explicitly excluded on Hemanth's request**; he will handle its source map separately.
- 35 raw workbook field rows, **32 distinct Farm–Tract–Field features in scope** after excluding Farm14043 and removing two duplicate field rows.
- 17 available candidate FSA source map previews for manual QA; 11 farm-map matches supported by printed Farm/Tract OCR, six still require exact-identifier confirmation.

## Verified geospatial features

| Farm ID | Producer | Tract | Field | FSA printed acres | Digitized acres | Error | Registration | Status |
|---|---|---|---|---:|---:|---:|---|---|
| 1778 | Robert Seaberry | 1334 | 6 | 14.31 | 14.318 | 0.06% | 180 inliers, 1.15 px RMSE; USGS NAIP | **Registered & visually QA passed** |
| 13653 | Jasper Summers | 5515 | 1 | 2.58 | 2.559 | 0.83% | 187 inliers, 0.53 px RMSE; USGS NAIP | **Registered & visually QA passed** |
| 14048 | Tarsha Mosley | 46008 | 1 | 0.89 | 0.868 | 2.44% | 68 inliers, 0.42 px RMSE; USGS NAIP | **Registered & visually QA passed** |

**Verified field polygons: 3 of 32. Awaiting independent geometry verification: 29.**

### Data and review images
- [Digitized, QA-passed GeoJSON](../geojson/orangeburg_registered_fields.geojson)
- [Farm1778 source-FSA yellow boundary compared to traced polygon](orangeburg_farm1778_field6_candidate_source.jpg)
- [Farm1778 field polygon laid over independent USGS aerial imagery](orangeburg_farm1778_field6_candidate_satellite.jpg)
- [Jasper Summers Tract5515 Field1 overlay](orangeburg_farm13653_tract5515_field1_candidate_satellite.jpg)
- [Tarsha Mosley Tract46008 Field1 overlay](orangeburg_farm14048_field1_candidate_satellite.jpg)
- [17 FSA scanned-map source preview sheets](orangeburg_fsa_review_previews/review_manifest.json)
- [Official U.S. Census Orangeburg County boundary](../geojson/orangeburg_county_boundary.geojson)
- [Farm/Tract/Field source inventory](orangeburg_source_inventory.json)

## Important unresolved issues
1. Source FSA PDFs are flattened scans rather than GeoPDFs; no farm polygon is counted until a geometric image registration and individual field boundary reconstruction both pass review.
2. Jasper Summers Farm13653 source contains both **Tract5515**, which is requested, and **Tract5516**, which is *not* requested. The 289-inlier match to Tract5516 was excluded; independent 187-inlier Tract5515 source-page registration and 2.559-acre field trace have now passed QA.
3. Margaret Berry Farm11782 FSA first page has **Field13 7.53 acres**, but a tentative outline yields about 15 acres despite strong satellite registration; **hold** until the correct interior field perimeter is established. The second PDF page unexpectedly depicts **Farm13225 Tract6178**, a different producer's map, and must not be treated as another Farm11782 field.
4. Christine Ziegler Farm1271 did not match the first recent-imagery search; its map may require historical basemaps, a larger search radius or manual landmarks.
5. Louie Johnson Farm8242 candidate correspondences were geometrically degenerate and rejected.
6. Source spreadsheet coordinates for Farms **9231**, **10262**, and **14291** are outside the 2024 Census Orangeburg County polygon. They may be residential coordinates; confirm the actual FSA field county independently rather than omitting these farms.
7. Six farm-PDF matches rely on names; they must be checked against printed Farm/Tract numbers.
8. Final deliverables require **two professional PDF atlases (satellite and topography)** with county overview and zoomed field polygons plus legend, not merely screenshots of FSA source PDFs. These atlases are **not yet complete**; do not represent this QA ledger as a finished atlas.

## Acceptance gates for each of the 29 outstanding features
1. Farm/Tract/Field ID matches workbook and printed source map.
2. Aerial georegistration is nondegenerate and visually aligned with distinctive permanent features.
3. Individual **field** boundary, not whole-farm tract, traced from source.
4. Traced area agrees reasonably with the printed FSA acreage; discrepancies documented for correction.
5. County membership checked against official county polygon; GPS hints never substituted for field geometry.
6. Only then append to [verified Orangeburg GeoJSON](../geojson/orangeburg_registered_fields.geojson) and include on both atlas backgrounds.

FSA-map-derived outlines are not cadastral or legal property surveys.
