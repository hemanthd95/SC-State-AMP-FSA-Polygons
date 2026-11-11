# SC State AMP — Farmer recovery Batch 1 (five producers)
**Updated:** November 11, 2026  
**Repository:** [SC-State-AMP-FSA-Polygons](https://github.com/hemanthd95/SC-State-AMP-FSA-Polygons)

## Completed files and QA accounting
- Five farmer GIS folders with one shapefile each (EPSG:4326), county topographic PDF, satellite field PDF, GeoJSON and QA.
- Source-registered **new** FSA features in this batch: **8** (Charles Bright Jr. 3; Joseph Gadson 2; Arthur Cobbs 1; Jasper Summers 2).
- Existing Jasper Summers and Margaret Berry features reused, not recounted as new.
- Five farmers reviewed; **zero Year 2 farmers administratively closed** because enrolled field selections or old area QA remain unresolved.
- **44 Year 2 farmers remain in the follow-up queue.** A new registered field is not a newly completed *farmer*.
- [Download current combined ZIP (all five folders)](../deliverables/AMP_Batch1_Five_Farmer_GIS_20261111.zip)  
- [Field-by-field QA CSV](../deliverables/batch1_five_farmer_recovery_20261111/Batch1_Farmer_QA.csv)  
- [Build summary JSON](../deliverables/batch1_five_farmer_recovery_20261111/BATCH1_BUILD_SUMMARY.json)

## Per-farmer source and completion matrix

| Farmer | New source-registered fields | Independent image match | Area checks | Remaining closure blockers |
|---|---|---|---|---|
| Charles Bright Jr. | Farm 2715 / Tract 3022 / Field 2; Tract 3021 / Fields 4 and 7 | Tract 3022: 281 NAIP inliers, 0.729px; Tract 3021: 148, 0.639px | Field2 5.367 vs 5.23 ac; Field4 3.153 vs 3.48; Field7 30.791 vs 30.82 | Year2 selected Field ID blank; Tract3022 Fields 9,10,3 not individually admitted; Tract3021 Field6 rough trace ~18% larger than FSA 0.96 ac and excluded |
| Joseph Gadson | Farm 4547 / Tract 4482 / Fields 3 and 4 | 251 NAIP inliers; 0.442px | Field3 1.912 vs 1.88 ac; Field4 0.573 vs 0.60 | Year2 Farm/Tract/Field blank; source Fields 12,10,9 not yet admitted |
| Arthur Cobbs | Farm 548 / Tract 295 / Field 1 | 48 NAIP inliers, 0.552px | 1.896 vs 1.80 ac | Master Year2 selected field blank; mapped source Field1 cannot by itself prove enrolled Field1 |
| Jasper Summers | Farm 13709 / Tract 45512 / Fields 16 and 27 | 130 NAIP inliers, 0.366px | Field16 2.349 vs 2.34 ac; Field27 0.186 vs 0.20 | Master selected field blank. Previously registered Farm13709/Tract45514 Fields8/17 and older Farm13653 retained; distinguish FSA source inventory from 8-acre enrollment selection |
| Margaret Berry | No new polygon in this batch; previously mapped Farm10939 Field3 and Farm11782 Field13 retained | Earlier NAIP registrations retained | Field3 1.566 vs FSA 1.57 ac; older Field13 physical polygon ~13.1 ac vs FSA 7.53 ac | Field13 boundary/eligible-acreage discrepancy unresolved; do not shrink polygon simply to force area match |

## Assurances
1. Geospatial location is based on independent NAIP matches and ground/geographic controls. **Ignore the county printed on the FSA office map** when determining physical field location.
2. Fields are never assigned by residential address alone.
3. Photo-traced FSA boundaries are research-planning approximations, **not legal surveys**.
4. Source outlines with inconsistent acreage or unproven enrollment selection remain **open**.
5. Reused farm shapefiles do not contribute new-farmer completion counts.
6. Satellite map PDFs must include two sourced road labels, a north arrow and scale bar.

## Batch 2 opening record: Javeiann (Jaivean) Spann
- Two user-supplied 2026 FSA images.
- Enrolled Year2 AMPSC029: **Farm 3988 / Tract 4673 / Field 1 (9.35 ac)**; adjacent Field4 0.29 ac.
- Second source: **Farm9447/Tract8142**, with unlabeled areas; do not conflate.
- Source image outlines digitized, **but no defensible WGS84 geographic registration yet**. Previously ranked road-intersection NAIP sites are only candidates and not accepted field locations.
- [Source-coordinate and identity QA](../analysis/recovery49_20261111/Jaivean_Spann/SOURCE_PIXEL_TRACES_AND_ID_RECONCILIATION.json)
- Javeiann is **not completed**. She leads the next batch of five.

## Next work
- Prioritize resolving exact selected field IDs for Charles Bright Jr., Joseph Gadson and Arthur Cobbs using the enrollment database / producer confirmation.
- Confirm Margaret Berry's Farm11782 acreage discrepancy with original CLU source instead of manufacturing a new polygon.
- Resolve Jasper Summers enrolled field selection vs total listed source tracts.
- For Javeiann, use independent aerial/road/parcel controls, check her Field1 calculated acreage versus 9.35 ac, and create her Weekley-style shapefile only after a valid geographic match.
