#!/usr/bin/env bash

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

flight_id="e48d496c-e7d1-4345-8fc2-42fbc78b3b28"
data_root="/project/dash_drone/user/stephen.amerige/dpu-data/odm/${flight_id}"

python "$script_dir/map-flight-images.py" \
    "$script_dir/flight-document.txt" \
    "$data_root/images" \
    --output "$script_dir/flight-image-map.csv"
