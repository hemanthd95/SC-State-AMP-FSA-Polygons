**Williamsburg correction:** The earlier four-entry map was wrong for the county workbook. The corrected map contains only Farms 17615 and 10519, from Sheet1 rows 2 and 3. Master-only IDs 17614 and 5611 are excluded. Master records remain audit evidence, not extra county-map farms. Other county source reviews still require county-roster validation.

[Corrected Williamsburg three-page PDF](corrected_county_atlases/Williamsburg/Williamsburg_County_Two_Farm_Source_Imagery_Atlas.pdf) | [Williamsburg atlas and GIS ZIP](corrected_county_atlases/Williamsburg/Williamsburg_Corrected_Atlas_and_GIS.zip)

# AMP/FSA source-review delivery — November 3, 2026

**Private source-review and GIS outputs. The requested final satellite/topographic atlases are not complete.**

The package contains 30 source-review PDFs (163 pages), corrected GIS exports, source reconciliation, exception reports and reproducible scripts. The PDF insets show supplied FSA source maps. Scanned maps are not falsely overlaid at invented coordinates. No source contact/tax forms are included.

## Downloads

- [Complete source-review package: PDFs, GIS, QA and scripts](SC_AMP_Source_Review_and_GIS.zip)
- [GIS layers and quality reports](SC_AMP_GIS_Layers_and_QA.zip)
- [Orangeburg source-review PDF (48 pages)](source_review_pdfs/Orangeburg_County_Source_Review.pdf)
- [Verification and outstanding requirements](qa/verification_report.md)
- [Machine-readable completion status](qa/completion_status.json)

For a ZIP, open its GitHub file page and select **Download raw file**. For a PDF, use GitHub's PDF preview or its download button. Sign in with access to this private repository. Cloud-environment publication is not required to download these repository files.

## Individual county review PDFs

- [Aiken — 3 pages](source_review_pdfs/Aiken_County_Source_Review.pdf)
- [Allendale — 5 pages](source_review_pdfs/Allendale_County_Source_Review.pdf)
- [Anderson — 2 pages](source_review_pdfs/Anderson_County_Source_Review.pdf)
- [Bamberg — 4 pages](source_review_pdfs/Bamberg_County_Source_Review.pdf)
- [Barnwell — 2 pages](source_review_pdfs/Barnwell_County_Source_Review.pdf)
- [Berkeley — 9 pages](source_review_pdfs/Berkeley_County_Source_Review.pdf)
- [Calhoun — 3 pages](source_review_pdfs/Calhoun_County_Source_Review.pdf)
- [Charleston — 3 pages](source_review_pdfs/Charleston_County_Source_Review.pdf)
- [Cherokee — 2 pages](source_review_pdfs/Cherokee_County_Source_Review.pdf)
- [Clarendon — 14 pages](source_review_pdfs/Clarendon_County_Source_Review.pdf)
- [Colleton — 5 pages](source_review_pdfs/Colleton_County_Source_Review.pdf)
- [Darlington — 4 pages](source_review_pdfs/Darlington_County_Source_Review.pdf)
- [Dorchester — 7 pages](source_review_pdfs/Dorchester_County_Source_Review.pdf)
- [Florence — 5 pages](source_review_pdfs/Florence_County_Source_Review.pdf)
- [Greenville — 3 pages](source_review_pdfs/Greenville_County_Source_Review.pdf)
- [Greenwood — 4 pages](source_review_pdfs/Greenwood_County_Source_Review.pdf)
- [Hampton — 5 pages](source_review_pdfs/Hampton_County_Source_Review.pdf)
- [Horry — 3 pages](source_review_pdfs/Horry_County_Source_Review.pdf)
- [Jasper — 4 pages](source_review_pdfs/Jasper_County_Source_Review.pdf)
- [Lexington — 2 pages](source_review_pdfs/Lexington_County_Source_Review.pdf)
- [Marion — 4 pages](source_review_pdfs/Marion_County_Source_Review.pdf)
- [Marlboro — 2 pages](source_review_pdfs/Marlboro_County_Source_Review.pdf)
- [Orangeburg — 48 pages](source_review_pdfs/Orangeburg_County_Source_Review.pdf)
- [Richland — 2 pages](source_review_pdfs/Richland_County_Source_Review.pdf)
- [Saluda — 2 pages](source_review_pdfs/Saluda_County_Source_Review.pdf)
- [Spartanburg — 3 pages](source_review_pdfs/Spartanburg_County_Source_Review.pdf)
- [Sumter — 6 pages](source_review_pdfs/Sumter_County_Source_Review.pdf)
- [Unassigned — 2 pages](source_review_pdfs/Unassigned_County_Source_Review.pdf)
- [Williamsburg — 3 pages](source_review_pdfs/Williamsburg_County_Source_Review.pdf)
- [York — 2 pages](source_review_pdfs/York_County_Source_Review.pdf)

## Scope and limitations

The 23 county workbooks contain 110 records and 77 county-scoped Farm IDs. The broader current/historical enrollment union has 120 county/Farm-ID combinations after six supported county corrections, plus four unresolved enrollment rows without Farm IDs. These counts do not establish 120 distinct current participating farms.

All 22 registered source-field polygons were corrected against their GeoPDF metadata and independently checked against GDAL's interpretation. All six source farm groups match the corrected enrollment inventory. Other farm boundaries remain null. Field-level program enrollment and source identity exceptions are documented in QA.

USGS/NAIP background access remains blocked in the cloud runtime, and scanned-map registration and source identity issues remain unresolved. This delivery does not contain final Satellite/Topography atlases or a completed production atlas ZIP.

The reusable scripts are also saved under the repository's root `scripts/` directory on this branch. Original source documents and original repository GeoJSON are preserved. See the packaged README for reproduction requirements.
