# SC State AMP — Recovery Batch 2 (Five Farmers)

**Date:** November 11, 2026  
**Completion standard:** Exact enrolled FSA Farm–Tract–Field location required, approximate aerial/photo boundary tolerated up to 25% acreage difference. No residential-address-point polygons, no invented field numbers.

## Verified outputs

- **Batch 2 combined ZIP:** [AMP_Recovery49_Batch2_Five_Farmer_20261111.zip](../deliverables/AMP_Recovery49_Batch2_Five_Farmer_20261111.zip) — currently three farmers with actual geo-registered source polygons (Christine, Tywone, Joe), and two source-review-only records (Javeiann, Calvin).
- **Batch 2 authoritative five-farmer QA:** [Batch2_Five_Farmer_QA.csv](../deliverables/recovery49_batch2_five_20261111/Batch2_Five_Farmer_QA.csv)
- **Build summary:** [BUILD_SUMMARY.json](../deliverables/recovery49_batch2_five_20261111/BUILD_SUMMARY.json)

| Farmer | Registered FSA source fields | FSA acreage -> traced acreage | Year 2 enrollment closure |
|---|---|---|---|
| Christine Berry Zeigler | Farm **1271** / Tract **469** / Field **1** | 10.51 -> **11.128 ac** (+5.88%) | **CLOSED against known Year 2 field**. Farm/Tract printed source footer independently inspected, NAIP image registration 217 matches/1.28 px. |
| Joe Hilliard | Farm **13859** / Tract **45814** / Field **36** | 25.32 -> **24.312 ac** (-3.98%) | **OPEN**: Year 2 selected **Field 20** not present on available photo. An alternate PDF is the correct Farm 13859, registered with 83 NAIP matches / 1.179 px. His other PDF Farm 6528 is a separate farm and cannot be substituted. |
| Tywone Hilliard | Farm **3873** / Tract **3895** / Field **4**; Farm **4261** / Tract **5953** / Field **2**; Farm **960** / Tract **3812** / Field **1** | 1.93 -> 2.030 ac; 2.10 -> 2.254 ac; 3.41 -> 3.817 ac | **OPEN**: Year 2 asks for Farms **1064** and **3826**. These three georegistered source fields (188–232 NAIP matches) are not the enrolled farms. |
| Calvin Blair | Source Farm **3603** / Tract **848** / Field **3** | 12.50 ac; no accepted geographic field yet | **OPEN**: short-range NAIP match degenerate. Broader address-first aerial search submitted to GitHub Actions. |
| Javeiann Spann | Digitized source Farm **3988** / Tract **4673** / Field **1**; separate map Farm 9447 / Tract 8142 | 9.35 ac source; no accepted geographic field yet | **OPEN**: source-photo pixels are not a WGS84 polygon and no independent NAIP location has been identified. |

## Completion totals

- Starting follow-up queue (after Batch 1): **44 unique farmers**.
- Finished known Year 2 target during Batch 2: **1 (Christine Berry Zeigler)**.
- **Still requiring follow-up: 43** unique farmers, including Joe, Tywone, Calvin, and Javeiann. 
- **Mapped source farmer count in Batch 2:** 3. This is **not** the same as the number of completed enrolled farmers.
- Existing older deliveries are retained; no double counting of farmer folders.

## Geospatial standards / method

1. The Excel farm address is a starting point for searching only; the FSA office county printed on a PDF is not used to infer physical county.
2. Georeferencing uses independent NAIP satellite/aerial feature correspondences; physical county is checked against U.S. Census geospatial boundaries.
3. Source FSA Farm/Tract/Field IDs must be confirmed before a farmer is marked completed. A mapped source field with different identifiers remains partial.
4. Approximate visually defensible FSA crop boundary may depart by **up to 25%** from printed acreage; do not resize polygons artificially to meet an acreage.
5. Mapped farmer folders include EPSG:4326 shapefiles, GeoJSON, county topographic and road-labeled satellite PDFs; source-only records never contain invented geographic polygons.
6. These outputs are research-planning geometries, **not legal cadastral surveys**.

## Searches and pending evidence

- Joe correct Farm 13859 regional NAIP search completed successfully; [registration QA](../analysis/recovery49_20261111/batch2/joe_enrolled_farm13859_registration/joe_correct_enrolled_farm_registration_QA.json).
- Calvin Farm 3603 wider search is recorded under [analysis/recovery49_20261111/batch2/calvin_wide_match](../analysis/recovery49_20261111/batch2/calvin_wide_match/) after its GitHub workflow finishes; do not assume completion before reading QA.
- Javeiann source pixels and exact enrolled identifiers: [Spann source QA](../analysis/recovery49_20261111/Jaivean_Spann/SOURCE_PIXEL_TRACES_AND_ID_RECONCILIATION.json).

**Important:** GitHub Actions completion means processing finished, not all farmers passed geographic QA. Always consult the results and five-farmer QA register.
