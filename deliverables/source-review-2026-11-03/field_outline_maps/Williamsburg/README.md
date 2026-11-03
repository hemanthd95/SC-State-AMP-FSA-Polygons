# Williamsburg extracted-field GIS maps

Farm roster: exactly two records from Williamsburg County_Producers.xlsx, rows 2 and 3: Farm 17615 / Tract 5419 and Farm 10519 / Tract 3979.

The actual PDFs contain seven field outlines for Farm 17615 and two for Farm 10519. All nine closed paths were freshly extracted from the PDFs, matched to printed field IDs and acreage, transformed using their GeoPDF geographic metadata, and exported to GeoJSON/Shapefile. The field IDs listed in Excel are separately flagged; other source fields do not create additional farms or assumed enrollment records.

The three-page atlas has a two-marker county overview and one GIS detail map per farm. Detail backgrounds contain only the georeferenced imagery extracted from the PDFs. Original PDF vector lines and text were disabled for background rendering; the map outlines, field labels, north arrows, scale bars and acreage tables were newly drawn from the extracted GIS data.

The county overview uses a Census boundary, not county-wide satellite imagery. The USGS topographic version remains unavailable because its service is blocked by the cloud network proxy. No topographic image is synthesized from aerial imagery.
