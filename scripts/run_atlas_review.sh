#!/usr/bin/env bash
set -euo pipefail
cd /workspace/SC-State-AMP-FSA-Polygons
atlas_python=/workspace/amp-atlas-venv/bin/python
atlas_boundary=/workspace/amp-atlas-work/census_counties_2022.json
mkdir -p /workspace/amp-atlas-work
if [[ ! -f "$atlas_boundary" ]]; then
    curl --fail --location --silent --show-error --max-time 180 \
      'https://raw.githubusercontent.com/uscensusbureau/citysdk/fc5d7880529fedcde181269fc5d518767221281e/v2/GeoJSON/500k/2022/county.json' \
      --output "${atlas_boundary}.download"
    echo "7380c3f50bcfbe395a355837582e515320bb89ee0550efbf0bb42fee2da56c49  ${atlas_boundary}.download" | sha256sum --check --status
    mv "${atlas_boundary}.download" "$atlas_boundary"
fi
echo "7380c3f50bcfbe395a355837582e515320bb89ee0550efbf0bb42fee2da56c49  ${atlas_boundary}" | sha256sum --check --status
"$atlas_python" scripts/atlas_sources.py
"$atlas_python" scripts/atlas_inventory.py
"$atlas_python" scripts/atlas_geopdf.py
"$atlas_python" scripts/atlas_match_sources.py
"$atlas_python" scripts/atlas_export_gis.py
"$atlas_python" scripts/atlas_review_pdfs.py
"$atlas_python" scripts/atlas_delivery.py
