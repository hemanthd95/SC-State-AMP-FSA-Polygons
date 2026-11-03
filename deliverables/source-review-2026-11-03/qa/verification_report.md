# SC AMP/FSA verification report

**Status: partial source-review and GIS delivery. Final satellite and topographic atlases are not complete.**

## Reconciled scope

- Downloaded all 144 source files from private repository commit `60bc244`: 110 PDFs, 25 XLSX workbooks, 3 CSVs, 6 images.
- Inspected/OCR-processed 217 PDF/image pages. Administrative, contact and tax forms are excluded from map insets.
- The 23 county workbooks contain 110 records and 77 county-scoped Farm IDs.
- The raw union initially contained 122 county/Farm-ID combinations. 6 source-supported county corrections yield 120 listed combinations across 28 counties. These are not independently confirmed unique current farms. See `county_assignment_corrections.csv`.
- Four enrollment rows lack Farm IDs: two Orangeburg, one Saluda, one without a county. They remain visible as unresolved enrollment records; they are not invented farm identities.
- Current and historical enrollment scopes remain distinct in the inventory and county indices.

## Geometry findings

The 22 preliminary polygons passed basic shape/acreage checks but had a north-south reference reversal. The corrected exported coordinates were reproduced directly from original vector drawings using GeoPDF GPTS/LPTS and viewport coordinates. All 22 source hashes and all 22 printed field/acreage pairs were checked. Twenty-one acreage-label centers lie inside their source paths; the remaining narrow field uses a printed leader, confirmed visually in an independent Poppler rendering. The original repository layers were preserved. Maximum change from a legacy boundary: 762.5 m. Maximum agreement difference from independent GDAL metadata interpretation: 0.0000780 m. This is agreement between transforms, not absolute positional accuracy. Maximum recomputed acreage difference: 0.876%; maximum corner-fit residual: 0.280 m.

There are six source-map farm groups, 6 matched to the supplied enrollment identifier inventory after source-supported county corrections. Farm 8185 was listed under Florence; its scanned source footer confirms Farm 8185 / Tract 2352, and the matching GeoPDF explicitly references Darlington County. Both affected enrollment rows were corrected with original values preserved. Farm boundaries unresolved for the other 114 listed combinations are null geometries. No buffers, rectangles or relocated polygons were fabricated. Source fields are not automatically treated as enrolled program fields; see the field crosswalk.

## What the PDFs contain

30 source-review PDFs (165 pages) cover the 28 counties with Farm IDs, Saluda's unresolved record, and a separate unassigned-county record. Each overview lists every inventory entry and each entry has corresponding detail pages. Overviews use actual 2022 Census 1:500,000 county boundaries from the Census Bureau CitySDK data repository. Usable reported points are marked approximate; missing or outside-county coordinates are listed without invented map positions. FSA source-map insets retain visible field boundaries. Unregistered insets are not geographic overlays. Source identity conflicts and missing maps are explicitly labeled. Source image acquisition dates are not independently established. Some source photographs are blurred or oblique; page rendering does not fix source quality.

## Remaining production requirements

1. Enable working access to `basemap.nationalmap.gov` (USGS topography) and `naip.nationalmap.gov` (NAIP), and complete service/imagery date and print-use checks. Both HTTPS requests currently fail at the environment proxy with CONNECT 403. Network requirements have been saved in the configuration draft; the runtime still reports only the older Drive rules.
2. Reconcile county and Farm/Tract/Field conflicts, missing IDs and source matches. Four missing-ID enrollment rows and 17 Farm-ID combinations without a confirmed source map require review. 27 additional Farm-ID combinations have source-identity or county review flags.
3. Establish supported control points and registration error for scanned/photographed maps before any new geographic polygon admission. No scanned map has yet been independently geographically registered.
4. Generate both final basemap atlas versions, check alignment, render every final page, and verify acquisition dates, attributions and overview/detail correspondence.

The requested Orangeburg Satellite/Topography PDFs and final `SC_AMP_County_Farm_Atlases.zip` do not exist yet. The delivered ZIP is deliberately named as a source-review package.

## County accounting

| County | Listed Farm IDs | Missing-ID rows | Registered farm groups | Unresolved farm boundaries | Review pages | Satellite | Topography |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Aiken | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Allendale | 4 | 0 | 0 | 4 | 5 | Pending | Pending |
| Anderson | 1 | 0 | 0 | 1 | 2 | Pending | Pending |
| Bamberg | 3 | 0 | 0 | 3 | 4 | Pending | Pending |
| Barnwell | 1 | 0 | 1 | 0 | 2 | Pending | Pending |
| Berkeley | 8 | 0 | 0 | 8 | 9 | Pending | Pending |
| Calhoun | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Charleston | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Cherokee | 1 | 0 | 0 | 1 | 2 | Pending | Pending |
| Clarendon | 13 | 0 | 0 | 13 | 14 | Pending | Pending |
| Colleton | 4 | 0 | 0 | 4 | 5 | Pending | Pending |
| Darlington | 3 | 0 | 1 | 2 | 4 | Pending | Pending |
| Dorchester | 6 | 0 | 0 | 6 | 7 | Pending | Pending |
| Florence | 4 | 0 | 1 | 3 | 5 | Pending | Pending |
| Greenville | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Greenwood | 3 | 0 | 0 | 3 | 4 | Pending | Pending |
| Hampton | 4 | 0 | 0 | 4 | 5 | Pending | Pending |
| Horry | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Jasper | 3 | 0 | 0 | 3 | 4 | Pending | Pending |
| Lexington | 1 | 0 | 0 | 1 | 2 | Pending | Pending |
| Marion | 3 | 0 | 1 | 2 | 4 | Pending | Pending |
| Marlboro | 1 | 0 | 0 | 1 | 2 | Pending | Pending |
| Orangeburg | 34 | 2 | 0 | 34 | 48 | Pending | Pending |
| Richland | 1 | 0 | 0 | 1 | 2 | Pending | Pending |
| Saluda | 0 | 1 | 0 | 0 | 2 | Pending | Pending |
| Spartanburg | 2 | 0 | 0 | 2 | 3 | Pending | Pending |
| Sumter | 5 | 0 | 0 | 5 | 6 | Pending | Pending |
| Unassigned | 0 | 1 | 0 | 0 | 2 | Pending | Pending |
| Williamsburg | 4 | 0 | 2 | 2 | 5 | Pending | Pending |
| York | 1 | 0 | 0 | 1 | 2 | Pending | Pending |

## Validation

Every source-review PDF page was rasterized at 90 dpi, checked for nonblank output and page-bound text. Every overview identifier was checked against its detail page text; index/detail entry counts match. Contact sheets are supplied for visual inspection. These checks validate review-document structure, not final basemap alignment or complete geographic verification.
