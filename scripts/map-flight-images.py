#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Map flight JPEGs to MongoDB flight geometry points "
            "using EXIF GPS coordinates."
        )
    )

    parser.add_argument(
        "flight_document",
        type=Path,
        help="Saved MongoDB flight document",
    )

    parser.add_argument(
        "images_dir",
        type=Path,
        help="Directory containing original GUID-named JPEG images",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("flight-image-map.csv"),
        help="Output CSV filename",
    )

    return parser.parse_args()


def extract_mongo_points(path: Path) -> list[tuple[float, float]]:
    text = path.read_text(encoding="utf-8")

    start = text.index("flight_polygon:")
    end = text.index("flight_bounding_box:")

    polygon = text[start:end]

    pattern = re.compile(
        r"coordinates:\s*\[\s*"
        r"(?:Double\()?['\"]?(-?\d+(?:\.\d+)?)['\"]?\)?\s*,\s*"
        r"(?:Double\()?['\"]?(-?\d+(?:\.\d+)?)['\"]?\)?\s*"
        r"\]",
        re.MULTILINE,
    )

    points = [
        (float(lon), float(lat))
        for lon, lat in pattern.findall(polygon)
    ]

    if not points:
        raise RuntimeError("No MongoDB geometry points found")

    return points


def extract_images(images_dir: Path) -> list[dict]:
    command = [
        "exiftool",
        "-j",
        "-n",
        "-FileName",
        "-DateTimeOriginal",
        "-SubSecDateTimeOriginal",
        "-CreateDate",
        "-GPSLatitude",
        "-GPSLongitude",
        str(images_dir),
    ]

    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
    )

    records = json.loads(result.stdout)

    images = []

    for record in records:
        filename = record.get("FileName")
        latitude = record.get("GPSLatitude")
        longitude = record.get("GPSLongitude")

        timestamp = (
            record.get("SubSecDateTimeOriginal")
            or record.get("DateTimeOriginal")
            or record.get("CreateDate")
        )

        if filename is None:
            continue

        if latitude is None or longitude is None:
            raise RuntimeError(
                f"{filename}: GPS coordinates are missing"
            )

        if timestamp is None:
            raise RuntimeError(
                f"{filename}: capture timestamp is missing"
            )

        images.append(
            {
                "filename": filename,
                "timestamp": timestamp,
                "latitude": float(latitude),
                "longitude": float(longitude),
            }
        )

    if not images:
        raise RuntimeError("No JPEG metadata records found")

    return images


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius = 6371008.8

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2) ** 2
    )

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a),
    )

    return radius * c


def find_nearest(
    image_lon: float,
    image_lat: float,
    mongo_points: list[tuple[float, float]],
) -> tuple[int, float]:
    best_index = None
    best_distance = None

    for index, (mongo_lon, mongo_lat) in enumerate(
        mongo_points,
        start=1,
    ):
        distance = haversine_m(
            image_lat,
            image_lon,
            mongo_lat,
            mongo_lon,
        )

        if best_distance is None or distance < best_distance:
            best_index = index
            best_distance = distance

    if best_index is None or best_distance is None:
        raise RuntimeError("Unable to find nearest Mongo point")

    return best_index, best_distance


def main() -> None:
    args = parse_args()

    mongo_points = extract_mongo_points(args.flight_document)
    images = extract_images(args.images_dir)

    print(f"Mongo geometry points: {len(mongo_points)}")
    print(f"JPEG images:           {len(images)}")

    if len(images) != len(mongo_points):
        raise RuntimeError(
            "Image count and Mongo geometry point count differ: "
            f"{len(images)} != {len(mongo_points)}"
        )

    # Capture-time order is retained only as a diagnostic.
    chronological = sorted(
        images,
        key=lambda item: (
            item["timestamp"],
            item["filename"],
        ),
    )

    timestamp_rank = {
        image["filename"]: rank
        for rank, image in enumerate(
            chronological,
            start=1,
        )
    }

    rows = []

    for image in images:
        mongo_index, nearest_distance = find_nearest(
            image["longitude"],
            image["latitude"],
            mongo_points,
        )

        mongo_lon, mongo_lat = mongo_points[mongo_index - 1]

        rows.append(
            {
                "mongo_index": mongo_index,
                "filename": image["filename"],
                "capture_time": image["timestamp"],
                "timestamp_rank": timestamp_rank[image["filename"]],
                "timestamp_rank_matches_mongo_index": (
                    timestamp_rank[image["filename"]]
                    == mongo_index
                ),
                "image_longitude": image["longitude"],
                "image_latitude": image["latitude"],
                "mongo_longitude": mongo_lon,
                "mongo_latitude": mongo_lat,
                "gps_difference_m": nearest_distance,
            }
        )

    # Put the CSV into actual flight/Mongo order.
    rows.sort(key=lambda row: row["mongo_index"])

    assignments = [
        row["mongo_index"]
        for row in rows
    ]

    counts = Counter(assignments)

    duplicate_assignments = {
        index: count
        for index, count in counts.items()
        if count > 1
    }

    assigned = set(assignments)

    unassigned = [
        index
        for index in range(1, len(mongo_points) + 1)
        if index not in assigned
    ]

    distances = [
        row["gps_difference_m"]
        for row in rows
    ]

    timestamp_mismatches = [
        row
        for row in rows
        if not row["timestamp_rank_matches_mongo_index"]
    ]

    with args.output.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=rows[0].keys(),
        )

        writer.writeheader()
        writer.writerows(rows)

    print()
    print(f"Mapping written:            {args.output}")
    print(f"Unique Mongo assignments:   {len(assigned)}")
    print(f"Duplicate assignments:      {len(duplicate_assignments)}")
    print(f"Unassigned Mongo points:    {len(unassigned)}")
    print(
        "Maximum GPS difference:    "
        f"{max(distances):.3f} m"
    )
    print(
        "Mean GPS difference:       "
        f"{sum(distances) / len(distances):.3f} m"
    )
    print(
        "Timestamp/order mismatches: "
        f"{len(timestamp_mismatches)}"
    )

    if duplicate_assignments:
        print()
        print("Duplicate Mongo assignments:")

        for index, count in sorted(
            duplicate_assignments.items()
        ):
            filenames = [
                row["filename"]
                for row in rows
                if row["mongo_index"] == index
            ]

            print(
                f"  Mongo {index}: "
                f"{count} images: "
                + ", ".join(filenames)
            )

    if unassigned:
        print()
        print("Unassigned Mongo points:")

        print(
            "  "
            + ", ".join(
                str(index)
                for index in unassigned
            )
        )

    if timestamp_mismatches:
        print()
        print("Timestamp-order differences:")

        for row in timestamp_mismatches:
            print(
                f'  Mongo {row["mongo_index"]}: '
                f'{row["filename"]} '
                f'capture={row["capture_time"]} '
                f'timestamp-rank={row["timestamp_rank"]} '
                f'GPS-difference={row["gps_difference_m"]:.3f} m'
            )

    if duplicate_assignments or unassigned:
        raise RuntimeError(
            "GPS mapping is not one-to-one"
        )


if __name__ == "__main__":
    main()
