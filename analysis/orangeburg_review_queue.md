# Orangeburg AMP/FSA source review queue

Private SCSU mapping inventory. **None of these field polygons is registered by this audit.**

- 18 farms originally in roster; **17 in the current batch**, after excluding Mary Koon (Farm 14043) at the user's direction. **32 unique Farm–Tract–Field groups in scope**.
- Among the 17 farms in scope, 11 document-ID-confirmed source matches and 6 filename-only matches. The one missing FSA map belongs to excluded Farm 14043.
- Spreadsheet coordinates and addresses are approximate candidate search hints, not surveyed field locations. Use a mixture of near-farm aerial context, road landmarks, source FSA boundaries, Farm/Tract IDs and acreage for verification.
- Official Orangeburg County outline is from 2024 U.S. Census (GEOID 45075); never treat an out-of-county residential hint as proof that a farm should be removed from this county.

| Farm ID | Producer | Tract | Distinct fields | Best map file | Evidence |
|---|---|---|---|---|---|
| 1033 | Montez Hillard | 3879 | 3879/4 | Montez Hillard_FSA _Map.pdf | Filename only |
| 1271 | Christine Ziegler | 469 | 469/1 | Christine Berry Zeigler_FSA Map.pdf | Farm/Tract text |
| 1778 | Robert Seaberry | 1334 | 1334/6 | Robert Seaberry Jr. FSA.pdf | Farm/Tract text |
| 3873 | Tywone Hillard | 3895 | 3895/1, 3895/4 | Tywone Hillard_FSA_Map.pdf | Filename only |
| 8242 | Louie Johnson | 5134 | 5134/2 | Louie Johnson FSA_Map.pdf | Farm/Tract text |
| 9231 | Pashona Rendell | 7908 | 7908/11, 7908/12 | Everett Rendell FSAmap.pdf | Filename only |
| 10262 | Marva Jackson | 10855 | 10855/24, 10855/26, 10855/28 | Mava Jackson_FSA map, (dragged).pdf | Farm/Tract text |
| 10939 | Mageret Berry | 43399 | 43399/3 | Margaret_Berry_FSA_Map.pdf | Filename only |
| 11782 | Mageret Berry | 6230 | 6230/13 | Margaret_Berry_FSA_Map.pdf | Farm/Tract text |
| 11990 | Anthron Williams | 44081 | 44081/6, 44081/7 | Antron Williams_FSA Map.pdf | Filename only |
| 13225 | Morgan Summers | 6178 | 6178/24 | Morgan summers_FSA_Map.pdf | Farm/Tract text |
| 13618 | Rosa Berry | 3260 | 3260/17, 3260/26 | Christine Berry Zeigler_FSA Map.pdf | Filename only |
| 13653 | Jasper Summers | 5515 | 5515/1 | Jasper Summers_FSA_Map.pdf | Farm/Tract text |
| 13709 | Veronica Hodges | 45508, 45511, 45512, 45513, 45514 | 45508/1, 45511/1, 45512/8, 45513/9, 45514/7, 45514/8 | Veronica Hodges FSA.pdf | Farm/Tract text |
| 14043 | Mary Koon | 46002 | 46002/4 | Not found | **EXCLUDED from this batch by user; user handling separately** |
| 14048 | Tarsha Mosley | 46008 | 46008/1 | Tarsha Mosley_FSA_Map.pdf | Farm/Tract text |
| 14187 | Bruce Jenkins | 46145 | 46145/22, 46145/46, 46145/52 | Bruce Jenkins_FSA Map.pdf | Farm/Tract text |
| 14291 | Edward Carson | 46266 | 46266/13, 46266/18, 46266/19 | Edward Carson_FSA Map.pdf | Farm/Tract text |

## Current review priorities (excluding Mary Koon)

1. Georeference and inspect printed FSA field boundaries on 11 OCR-confirmed sources. The four-farm aerial matching pilot starts with Farms 1271, 1778, 8242 and 13653.
2. Independently verify sources for Farms 1033, 3873, 9231, 10939, 11990, and 13618, whose best matches rely on filenames alone.
3. The official Census Orangeburg boundary check flags spreadsheet GPS hints for Farms **9231 Pashona Rendell**, **10262 Marva Jackson**, and **14291 Edward Carson** as outside the county. Do not discard these farms; their addresses may be residences, or the fields may be elsewhere. The FSA actual field image and tract data control final county assignment.
4. Farm 13618 Field 26 and Farm 13653 Field 1 are each duplicated in the spreadsheet; digitize each geometry only once.
5. Keep low-confidence or nongeoregistered features out of the deliverable polygon GeoJSON and printed county atlases. Maintain a field-level unresolved list and verify field area vs the original FSA document.

## Supporting audit artifacts

- Official county boundary: [orangeburg_county_boundary.geojson](../geojson/orangeburg_county_boundary.geojson)
- County coordinate screening: [orangeburg_coordinate_screening.json](orangeburg_coordinate_screening.json)
- Private source PDF previews (not geometrically registered): [orangeburg_fsa_review_previews](orangeburg_fsa_review_previews)
- Automated aerial matching pilot diagnostics: [orangeburg_registration_pilot.json](orangeburg_registration_pilot.json)
