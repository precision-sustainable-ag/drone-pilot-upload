#!/usr/bin/env python3
import argparse
import shutil
from pathlib import Path

KEEP_DIRS = {
    "images",
    "odm_orthophoto",
    "odm_dem",
    "odm_georeferencing",
    "odm_report",
    "odm_texturing",
    "other_files",
    "veg_indices",
    "panels",
}
KEEP_FILE_SUFFIXES = {".json", ".sh", ".txt"}


def is_flight_dir(p: Path) -> bool:
    # Treat any directory (not symlink) as a flight folder
    return p.is_dir() and not p.is_symlink()


def should_keep(entry: Path) -> bool:
    if entry.is_dir():
        return entry.name in KEEP_DIRS
    if entry.is_file():
        return entry.suffix.lower() in KEEP_FILE_SUFFIXES
    # sockets/fifos/etc → delete by default
    return False


def clean_flight_dir(flight_dir: Path, dry_run: bool = False) -> dict:
    """
    Remove top-level entries in a flight folder that are NOT in the keep set.
    Returns a summary dict with counts.
    """
    removed = 0
    kept = 0
    errors = 0

    print(f"\n==> Processing: {flight_dir}")
    for entry in flight_dir.iterdir():
        # Skip hidden '.' and '..' implicitly (Pathlib won't return them)
        if should_keep(entry):
            kept += 1
            print(f"  KEEP   {entry.relative_to(flight_dir)}")
            continue

        print(f"  REMOVE {entry.relative_to(flight_dir)}")
        if dry_run:
            removed += 1
            continue

        try:
            if entry.is_dir() and not entry.is_symlink():
                shutil.rmtree(entry)
            else:
                # includes files and symlinks
                entry.unlink(missing_ok=True)
            removed += 1
        except Exception as e:
            errors += 1
            print(f"    ! ERROR removing {entry}: {e}")

    return {"kept": kept, "removed": removed, "errors": errors}


def main():
    parser = argparse.ArgumentParser(
        description="Clean ODM flight folders, keeping only essential outputs."
    )
    parser.add_argument(
        "--station",
        required=True,
        help="Path to research-station directory containing flight folders (e.g., sandhills)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max number of flight folders to process (0 = all).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without deleting.",
    )

    args = parser.parse_args()
    station = (
        Path(f"/rs1/shares/cals-research-station/{args.station}/flights").expanduser().resolve()
    )

    if not station.exists() or not station.is_dir():
        raise SystemExit(f"Station path does not exist or is not a directory: {station}")

    # Enumerate flight directories (top-level dirs only)
    flight_dirs = sorted([p for p in station.iterdir() if is_flight_dir(p)])
    if args.limit and args.limit > 0:
        flight_dirs = flight_dirs[: args.limit]

    if not flight_dirs:
        print("No flight folders found to process.")
        return

    total_kept = total_removed = total_errors = 0
    print(f"Found {len(flight_dirs)} flight folder(s) to process under: {station}")
    if args.dry_run:
        print("** DRY RUN: no changes will be made **")

    for fdir in flight_dirs:
        summary = clean_flight_dir(fdir, dry_run=args.dry_run)
        total_kept += summary["kept"]
        total_removed += summary["removed"]
        total_errors += summary["errors"]

    print("\n== Summary ==")
    print(f"Kept items:    {total_kept}")
    print(f"Removed items: {total_removed} {'(preview only)' if args.dry_run else ''}")
    print(f"Errors:        {total_errors}")


if __name__ == "__main__":
    main()
