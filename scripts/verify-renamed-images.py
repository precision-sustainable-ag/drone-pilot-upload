#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import re
from collections import Counter
from pathlib import Path


INDEX_RE = re.compile(r"-(\d{12})\.jpg$", re.IGNORECASE)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify that renamed flight images match the authoritative "
            "Mongo/GPS image mapping."
        )
    )

    parser.add_argument(
        "mapping_csv",
        type=Path,
        help="CSV produced by map-flight-images.py",
    )

    parser.add_argument(
        "source_dir",
        type=Path,
        help="Directory containing original GUID-named JPEG images",
    )

    parser.add_argument(
        "renamed_dir",
        type=Path,
        help="Directory containing Mongo-index-renamed JPEG images",
    )

    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def load_mapping(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    if not rows:
        raise RuntimeError(f"Mapping CSV is empty: {path}")

    required = {
        "mongo_index",
        "filename",
        "capture_time",
    }

    missing = required - set(rows[0])

    if missing:
        raise RuntimeError(
            "Mapping CSV is missing required columns: "
            + ", ".join(sorted(missing))
        )

    return rows


def index_from_filename(path: Path) -> int | None:
    match = INDEX_RE.search(path.name)

    if match is None:
        return None

    return int(match.group(1))


def main() -> None:
    args = parse_args()

    if not args.mapping_csv.is_file():
        raise RuntimeError(
            f"Mapping CSV not found: {args.mapping_csv}"
        )

    if not args.source_dir.is_dir():
        raise RuntimeError(
            f"Source directory not found: {args.source_dir}"
        )

    if not args.renamed_dir.is_dir():
        raise RuntimeError(
            f"Renamed directory not found: {args.renamed_dir}"
        )

    rows = load_mapping(args.mapping_csv)

    mapping_by_index: dict[int, dict] = {}

    for row in rows:
        index = int(row["mongo_index"])

        if index in mapping_by_index:
            raise RuntimeError(
                f"Duplicate mongo_index in mapping CSV: {index}"
            )

        mapping_by_index[index] = row

    source_files = {
        path.name: path
        for path in args.source_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".jpg"
    }

    renamed_files = [
        path
        for path in args.renamed_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".jpg"
    ]

    renamed_by_index: dict[int, list[Path]] = {}

    invalid_names: list[str] = []

    for path in renamed_files:
        index = index_from_filename(path)

        if index is None:
            invalid_names.append(path.name)
            continue

        renamed_by_index.setdefault(index, []).append(path)

    expected_indices = set(mapping_by_index)
    actual_indices = set(renamed_by_index)

    duplicate_indices = {
        index: paths
        for index, paths in renamed_by_index.items()
        if len(paths) > 1
    }

    missing_indices = sorted(
        expected_indices - actual_indices
    )

    unexpected_indices = sorted(
        actual_indices - expected_indices
    )

    missing_source_files: list[str] = []
    content_mismatches: list[tuple[int, str, str]] = []

    checked = 0

    for index in sorted(expected_indices):
        row = mapping_by_index[index]
        source_name = row["filename"]

        source_path = source_files.get(source_name)

        if source_path is None:
            missing_source_files.append(source_name)
            continue

        candidates = renamed_by_index.get(index, [])

        if len(candidates) != 1:
            continue

        renamed_path = candidates[0]

        source_hash = sha256(source_path)
        renamed_hash = sha256(renamed_path)

        checked += 1

        if source_hash != renamed_hash:
            content_mismatches.append(
                (
                    index,
                    source_name,
                    renamed_path.name,
                )
            )

    print(f"Source images:              {len(source_files)}")
    print(f"Mapped Mongo indices:       {len(mapping_by_index)}")
    print(f"Renamed images:             {len(renamed_files)}")
    print(
        "Expected indices present:   "
        f"{len(expected_indices - set(missing_indices))}"
        f"/{len(expected_indices)}"
    )
    print(f"Duplicate indices:          {len(duplicate_indices)}")
    print(f"Missing indices:            {len(missing_indices)}")
    print(f"Unexpected indices:         {len(unexpected_indices)}")
    print(f"Invalid renamed filenames:  {len(invalid_names)}")
    print(f"Missing source files:       {len(missing_source_files)}")
    print(f"Files content-checked:      {checked}")
    print(f"Content mismatches:         {len(content_mismatches)}")

    problems = False

    if duplicate_indices:
        problems = True
        print()
        print("Duplicate indices:")

        for index, paths in sorted(
            duplicate_indices.items()
        ):
            print(
                f"  {index}: "
                + ", ".join(path.name for path in paths)
            )

    if missing_indices:
        problems = True
        print()
        print("Missing indices:")
        print(
            "  "
            + ", ".join(
                str(index)
                for index in missing_indices
            )
        )

    if unexpected_indices:
        problems = True
        print()
        print("Unexpected indices:")
        print(
            "  "
            + ", ".join(
                str(index)
                for index in unexpected_indices
            )
        )

    if invalid_names:
        problems = True
        print()
        print("Invalid renamed filenames:")

        for name in invalid_names:
            print(f"  {name}")

    if missing_source_files:
        problems = True
        print()
        print("Missing source files:")

        for name in missing_source_files:
            print(f"  {name}")

    if content_mismatches:
        problems = True
        print()
        print("Content mismatches:")

        for index, source_name, renamed_name in content_mismatches:
            print(
                f"  Mongo {index}: "
                f"{source_name} != {renamed_name}"
            )

    if problems:
        raise SystemExit(
            "FAIL: renamed image set does not match "
            "the authoritative Mongo/GPS mapping."
        )

    print()
    print(
        "PASS: renamed image set matches the authoritative "
        "Mongo/GPS mapping."
    )


if __name__ == "__main__":
    main()
