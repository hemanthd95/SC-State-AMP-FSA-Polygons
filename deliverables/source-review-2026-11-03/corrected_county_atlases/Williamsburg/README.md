# Williamsburg county-workbook correction

The map roster is exactly the two rows in `Williamsburg County_Producers.xlsx`: Farm 17615 / Tract 5419 / Field 7 (row 2), and Farm 10519 / Tract 3979 / Field 5 (row 3).

The previous four-entry county review incorrectly included Farm 17614 (Year 1 master rows 7–9) and Farm 5611 (Year 1 master rows 63–65). Their IDs came from source records; adding them to this county map without reconciliation was an error. They are excluded here.

- [Corrected three-page source-imagery atlas](Williamsburg_County_Two_Farm_Source_Imagery_Atlas.pdf)
- [Exact county-workbook roster](Williamsburg_County_Roster.csv)
- [Excluded master records and provenance](Williamsburg_Excluded_Master_Records.csv)
- [Verification](Williamsburg_Verification.json)

The two selected field polygons and both farm source boundaries are included as GeoJSON. Nine source fields are retained in the context layer; only Fields 7 and 5 selected above are enrollment selections for this map. Other source field outlines do not represent extra farms or extra enrolled fields.

The imagery on detail pages is the actual supplied FSA aerial imagery, registered through GeoPDF metadata. The overview is a Census county-boundary map. The original request for separate county-wide satellite and USGS topographic backgrounds remains incomplete: external map-service access is still blocked. No topographic background is simulated.
