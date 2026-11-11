# SC State AMP — Farm recovery status register
**Updated:** 2026-11-11  
**Geography:** South Carolina, USA  
**Source of truth:** Year 2 producer roster reconciliation dated 2026-11-11, field-level geometry QA in this repository.

## Progress accounting (unique people, not ZIPs or fields)
- Year 2 unique farmers: **83**
- Farmers with at least one previously accepted mapped polygon: **42**
- Year 2 farmers requiring follow-up: **49** = **41** with no accepted polygon + **8** with mapped-but-unresolved QA/field gaps.
- Do not equate 49 with 49 entirely unworked farmers; do not count one person twice; do not increase completion numbers for new provisional source-only polygons.
- Rick Boswell was already among the original 39 per-farmer packages; not a new recovery.
- Antron Williams remains among the 49 outstanding (even though six **provisional** source fields have now been georeferenced).

## Antron Williams — Farm 11990, Tract 44081
- **Enrollment targets in Year 2 roster:** Fields **6 and 7**.
- **Cinnabar Road FSA page 5:** Fields **7, 18, 19, 20**.
  - TIGER/FSA road-curve fit over 13 independent roadway controls: 3.376 m source-road fit RMSE; source rotation ≈1.17°.
  - GeoJSON and Weekley-style shapefile/map created for Field **7** (1.226 ac vs 1.23 FSA), **18** (1.699 ac vs 1.68), **20** (1.584 ac vs 1.71).
  - **Field 19 deliberately excluded:** 0.803 ac rough trace vs 0.41 ac on FSA (95.94% deviation).
  - **Registration remains provisional:** no independent NAIP pixel-feature/SIFT confirmation, and the road-curve fit RMSE is not a full field positional accuracy assessment.
- **Gordon Drive FSA page 7:** Fields **61, 3, 16**.
  - Three-point source-to-NAIP registration; acreage agreement around 0.8–1.3%; status provisional, not surveyed.
  - **Do not interpret FSA Field 61 as Year 2 Field 6** without explicit source reconciliation.
- **One farmer deliverable:** [Combined 6-field Weekley folder ZIP](../deliverables/Antron_Williams_Combined_Provisional_Weekley_Folder_20261111.zip); contains EPSG:4326 farmer shapefile, topo county map, two separate satellite close-up pages, per-field GeoJSON, QA.
- Earlier separated field-group ZIPs remain for reproducibility.
- **Farmer status: PARTIAL / QA OPEN; NOT COMPLETED.** Missing: documented Year 2 Field 6 plus independent field-image positional check.

## Georeferencing acceptance rules
1. Use producer Excel **farm address as search anchor**, not the administrative county printed on the FSA map or the producer's mailing county.
2. Verify true field position from georeferenced NAIP/other orthophoto, cadastral boundaries, or repeated independent controls; don't place arbitrary polygon at residence address.
3. Match exactly by producer, FSA Farm, Tract, Field. Keep different aliases/identifiers distinct until demonstrated equivalent.
4. Compute geodesic acreage and polygon validity; record source date, registration residuals, imagery provider, QA and missing fields.
5. Categorize all products as **verified mapping**, **provisional location**, **source-pixel only**, or **unattempted**. Never mark farmer complete from a provisional layer alone.
6. Reuse previously verified GeoJSON and per-farmer outputs instead of rerunning finished work.
7. For accepted output: one shapefile per farmer, topo county-context PDF, satellite FieldMap PDF with at least two verified street labels. Multiple distinct fields may be on different close-up pages.
8. Exclude pages containing tax/producer identification from packages unless specifically requested.

## Next farm recovery review order (not claims of completion)
- **Quick verification candidates:** John Brabham (existing user-supplied farm-area GeoJSON; individual Field25 outstanding); Shane Middleton (mapped Farm14118 and source PDF for Farm9387, Fields5/7/11; confirm which are enrolled); John Lloyd (mapped Farms3756/4198, Farm4273 unresolved); Margaret Berry (mapped Farm11782, Farm10939 unresolved).
- **Then image/road matching:** remaining Orangeburg, Clarendon, Dorchester, and the other farms in the 49-farmer CSV. Sort these by existence of exact source Farm/Tract/Field map and verified address, not guessed ease from county.
- **Priority for Antron closure:** verify enrolled Field6 source identifier and refine Field19, and independently validate Cinnabar/Gordon aerial pixel alignment.

## Deliverables and baseline
- [Antron combined Weekley folder](../deliverables/Antron_Williams_Combined_Provisional_Weekley_Folder_20261111.zip)
- [Cinnabar road-fit QA](../deliverables/antron_williams_cinnabar_20261111/Cinnabar_Georegistration_QA.json)
- [Gordon road-fit QA](../deliverables/antron_williams_gordon_20261111/QA_Provisional_Gordon_Registration.json)
- [Original 39 per-farmer archive](../deliverables/SC_AMP_Per_Farmer_Weekley_Format_20261110.zip)
- Original 49-farmer follow-up CSV: `/mnt/data/fsa_audit_20261111/AMP_49_Farmer_Action_Queue.csv` in the working conversation; do not add to the repo without reviewing personal details.
