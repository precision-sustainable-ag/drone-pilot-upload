#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

flight_id="e48d496c-e7d1-4345-8fc2-42fbc78b3b28"

python "$script_dir/plot-opensfm-match-graph.py" \
    "$script_dir/flight-image-map.csv" \
    "$dpu/odm-atlas-full-20700919.out" \
    --output "$script_dir/opensfm-match-graph.png" \
    --csv "$script_dir/opensfm-match-pairs.csv" \
    --label-every 20 \
    --match-alpha 0.30 \
    --match-linewidth 0.70 \
    --atlas-wall 01:26:41 \
    --ceres-wall 02:53:06 \
    --atlas-cpu 03:14:25 \
    --ceres-cpu 12:59:36 \
    --atlas-memory 80.58 \
    --ceres-memory 77.17 \
    --title "OpenSfM matching - Sandhills flight $flight_id"
