#!/usr/bin/env bash

set -euo pipefail
shopt -s nullglob

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <start-index> <count> <directory>" >&2
    exit 1
fi

start="$1"
count="$2"
dest="$3"

if [[ ! "$start" =~ ^[0-9]+$ || ! "$count" =~ ^[0-9]+$ ]]; then
    echo "start-index and count must be non-negative integers" >&2
    exit 1
fi

if (( count < 1 )); then
    echo "count must be at least 1" >&2
    exit 1
fi

mkdir -p "$dest"

end=$((start + count - 1))

for ((i = start; i <= end; i++)); do
    printf -v suffix '%012d.jpg' "$i"

    matches=( *-"$suffix" )

    if (( ${#matches[@]} == 0 )); then
        echo "No image found for index $i" >&2
        exit 1
    fi

    if (( ${#matches[@]} > 1 )); then
        echo "Multiple images found for index $i" >&2
        exit 1
    fi

    cp -- "${matches[0]}" "$dest/"
done

echo "Copied $count images, indices $start through $end, to $dest"
