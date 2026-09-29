#!/usr/bin/env bash

set -euo pipefail

usage()
{
    cat >&2 <<EOF
Usage: $0 <mapping.csv> <source-directory> <destination-directory>

Example:
    $0 flight-image-map.csv \
        /project/dash_drone/user/stephen.amerige/dpu-data/odm/<flight-id>/images \
        /project/dash_drone/user/stephen.amerige/dpu-data/odm/<flight-id>/images-renamed
EOF
    exit 2
}

[[ $# -eq 3 ]] || usage

mapping_file=$1
source_dir=$2
dest_dir=$3

[[ -f "$mapping_file" ]] || {
    printf 'Mapping file not found: %s\n' "$mapping_file" >&2
    exit 1
}

[[ -d "$source_dir" ]] || {
    printf 'Source directory not found: %s\n' "$source_dir" >&2
    exit 1
}

mkdir -p "$dest_dir"

count=0

while IFS=$'\t' read -r mongo_index filename capture_time; do
    source_file="$source_dir/$filename"

    [[ -f "$source_file" ]] || {
        printf 'Source image not found: %s\n' "$source_file" >&2
        exit 1
    }

    if [[ "$capture_time" =~ ^([0-9]{4}):([0-9]{2}):([0-9]{2})[[:space:]]([0-9]{2}):([0-9]{2}):([0-9]{2}) ]]; then
        year="${BASH_REMATCH[1]}"
        month="${BASH_REMATCH[2]}"
        day="${BASH_REMATCH[3]}"
        hour="${BASH_REMATCH[4]}"
        minute="${BASH_REMATCH[5]}"
        second="${BASH_REMATCH[6]}"
    else
        printf 'Unrecognized capture time for %s: %s\n' \
            "$filename" "$capture_time" >&2
        exit 1
    fi

    # Use the camera's original UTC offset if available.
    offset=$(exiftool -s3 -OffsetTimeOriginal "$source_file")

    if [[ "$offset" =~ ^[+-]([0-9]{2}):([0-9]{2})$ ]]; then
        tz_hour="${BASH_REMATCH[1]}"
        tz_minute="${BASH_REMATCH[2]}"
    else
        # Keep the field structurally consistent, but do not invent a timezone.
        tz_hour="00"
        tz_minute="00"
    fi

    printf -v new_name \
        '%s%s%s-%s%s-00%s-%s%s-%012d.jpg' \
        "$year" "$month" "$day" \
        "$hour" "$minute" \
        "$second" \
        "$tz_hour" "$tz_minute" \
        "$mongo_index"

    printf '%s -> %s\n' "$filename" "$new_name"

    cp -- \
        "$source_file" \
        "$dest_dir/$new_name"

    ((++count))

done < <(
    python - "$mapping_file" <<'PY'
import csv
import sys

with open(sys.argv[1], newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        print(
            row["mongo_index"],
            row["filename"],
            row["capture_time"],
            sep="\t",
        )
PY
)

printf '\nCopied %d images to %s\n' "$count" "$dest_dir"
