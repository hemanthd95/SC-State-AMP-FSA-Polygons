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
| 3873 | Tywone Hillard | 3895 | 1 | 0.43 | 0.458 | 6.62% | 156 inliers, 0.95 px RMSE; USGS NAIP | **Registered & visually QA passed** |
| 3873 | Tywone Hillard | 3895 | 4 | 1.93 | 1.942 | 0.63% | 156 inliers, 0.95 px RMSE; USGS NAIP | **Registered & visually QA passed** |
| 13709 | Veronica Hodges | 45514 | 8 | 4.79 | 4.735 | 1.15% | 87 inliers, 0.44 px RMSE; USGS NAIP | **Registered & visually QA passed** |
| 1033 | Montez Hillard | 3879 | 4 | 8.67 | ~6.83 | Approximate FSA highlight | 115 inliers, 0.96 px RMSE; USGS NAIP | **Registered & practical outline review passed** |
| 11782 | Mageret Berry | 6230 | 13 | 7.53 | ~13.11 | Approximate FSA white outline | 201 inliers, 0.57 px RMSE; USGS NAIP | **Registered & practical outline review passed** |

**Atlas-accepted source-derived field polygons: 12 of 32 workbook records. Remaining workbook records: 20.** **Three** Marva Jackson entries are explicitly mapped by FSA to Darlington County and should not be depicted in Orangeburg. That leaves **17 unresolved workbook field targets that may belong in Orangeburg**. Last two traces are approximate visible FSA borders; detailed acreage reconciliation is not a requirement for the user's county map purpose.

### Data and review images
- [Digitized, QA-passed GeoJSON](../geojson/orangeburg_registered_fields.geojson)
- [Farm1778 source-FSA yellow boundary compared to traced polygon](orangeburg_farm1778_field6_candidate_source.jpg)
- [Farm1778 field polygon laid over independent USGS aerial imagery](orangeburg_farm1778_field6_candidate_satellite.jpg)
- [Jasper Summers Tract5515 Field1 overlay](orangeburg_farm13653_tract5515_field1_candidate_satellite.jpg)
- [Tarsha Mosley Tract46008 Field1 overlay](orangeburg_farm14048_field1_candidate_satellite.jpg)
- [Tywone Tract3895 Fields1 and4 original source geometry](orangeburg_farm3873_fields_candidate_source_zoom.jpg)
- [Tywone two field polygons on independent USGS satellite image](orangeburg_farm3873_fields_candidate_satellite.jpg)
- [Veronica Hodges Tract45514 Field8 yellow-line trace QA](orangeburg_veronica_field8_candidate_source.jpg)
- [Veronica Field8 polygon over independent USGS satellite imagery](orangeburg_veronica_field8_candidate_satellite.jpg)
- [Montez Farm1033 target FSA source photo aligned to independent NAIP](orangeburg_montez_farm1033_match_overlay.jpg)
- [Montez source Field4 boundary enlarged for review](orangeburg_montez_farm1033_field4_source_zoom.jpg)
- [17 FSA scanned-map source preview sheets](orangeburg_fsa_review_previews/review_manifest.json)
- [Official U.S. Census Orangeburg County boundary](../geojson/orangeburg_county_boundary.geojson)
- [Farm/Tract/Field source inventory](orangeburg_source_inventory.json)

## New FSA image registrations, 5 November 2026

| Farm ID | Producer | Tract | Field(s) | Source | Satellite-match evidence | Approximate tracing |
|---|---|---|---|---|---|---|
| 13618 | Rosa Berry | 3260 | 17, 26 | `Rosa_Berry_FSA_Map.jpeg` (previously missed by PDF-only inventory) | 69 inliers / 1.92 px; independent USGS NAIP; 26 field center is very close to workbook GPS | Both visible yellow FSA polygons manually outlined; ~1.97 and 7.63 ac |
| 14187 | Bruce Jenkins | 46145 | 46, 52 | `Bruce Jenkins_FSA Map.pdf` page 2 | 113 inliers / 1.09 px; independent USGS NAIP | Both visible yellow FSA polygons manually outlined; ~3.30 and 7.60 ac; source acreage approximate |

Farm14187 requested **Field22** is still absent from the printed map (the map appears to show Field32), so Field22 is not assigned an invented footprint. Farm13618 fields17/26 are now included; previous suspicion that no Rosa map was supplied was incorrect.

## Important unresolved issues
1. Source FSA PDFs are flattened scans rather than GeoPDFs; no farm polygon is counted until a geometric image registration and individual field boundary reconstruction both pass review.
2. Jasper Summers Farm13653 source contains both **Tract5515**, which is requested, and **Tract5516**, which is *not* requested. The 289-inlier match to Tract5516 was excluded; independent 187-inlier Tract5515 source-page registration and 2.559-acre field trace have now passed QA.
3. Margaret Berry Farm11782 / Tract6230 / Field13 — **included as approximate**: a clearly marked long white FSA Field13 perimeter was traced using a strong 201-inlier satellite registration. Digitized shape area differs from printed 7.53 acres, noted as approximation; no survey accuracy claimed. The separate PDF page depicting Farm13225 Tract6178 remains a different producer and has not been attributed to Margaret.
4. Christine Ziegler Farm1271 did not match the first recent-imagery search; its map may require historical basemaps, a larger search radius or manual landmarks.
5. Louie Johnson Farm8242 candidate correspondences were geometrically degenerate and rejected.
6. Source spreadsheet coordinates for Farms **9231**, **10262**, and **14291** are outside the 2024 Census Orangeburg County polygon. Crucially, both provided `Mava Jackson_FSA map, (dragged).pdf` pages explicitly say **Darlington County**: Marva's three workbook entries should not be inserted into Orangeburg simply because the spreadsheet lists them there. Edward Carson's FSA aerial says Orangeburg despite external GPS, so his field locations remain unresolved.
7. Six farm-PDF matches rely on names; they must be checked against printed Farm/Tract numbers.
8. **Anthron Williams Farm11990**: the only filename-matched PDF, `Antron Williams_FSA Map.pdf`, actually contains a producer-eligibility/subsidiary report, not a field map. A real **Farm11990 / Tract44081 / Fields6 and7** FSA aerial boundary map is needed to digitize these fields.
9. **Tywone Hillard Farm3873 / Tract3895 — resolved for Fields1 and4**: PDF page2 belongs to DIFFERENT **Farm4261 / Tract5953** and was rejected. Page1 matched independent imagery with **156 inliers / 0.95px RMSE**; boundaries traced, checked against USGS NAIP and accepted (Field1 0.458 vs 0.43 FSA acres; Field4 1.942 vs 1.93 FSA acres).
10. **Veronica Hodges Farm13709 — one requested field resolved**: the initial 3-page PDF did not show the requested Field numbers. A separate 21-page `Vronica Hodges_FSA_Map.pdf` was OCR-audited: pages16–20 cover the target tracts, and **page20 Tract45514 Field8 (4.79 FSA acres)** matches the workbook. The field was georeferenced with **87 inliers / 0.44px RMSE** and traced to **4.735 acres (1.15% difference)**; source-yellow and independent NAIP overlays passed. Other workbook requests (Tract45508 Field1, 45511 Field1, 45512 Field8, 45513 Field9, 45514 Field7) still lack matching printed field numbers in these 2024 maps and remain unverified.
11. **Montez Hillard Farm1033 / Tract3879 / Field4 — approximate boundary included**: requested Field4 is visible on original source page1. Independent NAIP registration uses 115 inliers and 0.96px RMSE. The manually marked orange enclosure was traced as a practical field boundary; not a legal/survey geometry. A precise FSA-export perimeter would still be an improvement.
12. **Edward Carson Farm14291 / Tract46266**: the source photo does label requested Fields13, 18 and19, but no nondegenerate satellite registration was found near the initial provided coordinates. Both coordinates are outside the county boundary; FSA page says Orangeburg County, so actual field location requires separate confirmation.
13. Final deliverables require **two professional PDF atlases (satellite and topography)** with county overview and zoomed field polygons plus legend, not merely screenshots of FSA source PDFs. These atlases are **not yet complete**; do not represent this QA ledger as a finished atlas.

## Practical acceptance gates for each of the 20 outstanding workbook features
1. Farm/Tract/Field ID matches workbook and printed source map.
2. Aerial georegistration is nondegenerate and visually aligned with distinctive permanent features.
3. Individual **field** boundary, not whole-farm tract, traced from source.
4. Traced polygon follows the visible FSA field outline at useful atlas scale; printed acreage is contextual, not a stringent polygon acceptance threshold.
5. County membership checked against official county polygon; GPS hints never substituted for field geometry.
6. Only then append to [mapped Orangeburg GeoJSON](../geojson/orangeburg_registered_fields.geojson) and include on both atlas backgrounds.

FSA-map-derived outlines are not cadastral or legal property surveys.
