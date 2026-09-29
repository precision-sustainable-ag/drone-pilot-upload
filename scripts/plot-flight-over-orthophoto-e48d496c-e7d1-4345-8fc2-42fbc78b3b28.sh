#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

flight_id="e48d496c-e7d1-4345-8fc2-42fbc78b3b28"
data_root="/project/dash_drone/user/stephen.amerige/dpu-data/odm/${flight_id}"

orthophoto="${data_root}/output-full-atlas/code/odm_orthophoto/odm_orthophoto.tif"

python "$script_dir/plot-flight-over-orthophoto.py" \
    "$orthophoto" \
    "$script_dir/flight-image-map.csv" \
    --output "$script_dir/flight-over-orthophoto.png" \
    --max-dimension 2000 \
    --label-every 20 \
    --show-summary \
    --camera-model 'DJI Zenmuse P1' \
    --platform 'Atlas L40S' \
    --processing-time '01:26:41' \
    --peak-memory 80.58
