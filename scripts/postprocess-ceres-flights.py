#!/usr/bin/env python3
"""Complete Ceres VARI/GLI and PNG previews for successful ODM Slurm jobs.

Run on an allocated Ceres compute node with NumPy and Rasterio in this Python
environment. Never silently retry partial vegetation-index results.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ORTHO = "odm/code/odm_orthophoto/odm_orthophoto.tif"
INDICES = ("odm/veg_indices/vari_image.tif", "odm/veg_indices/gli_image.tif")
PREVIEWS = ("previews/orthophoto.png", "previews/vari.png", "previews/gli.png")


def nonempty(path):
    return path.is_file() and path.stat().st_size > 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--flight-id", help="Limit processing to one flight UUID")
    args = parser.parse_args()
    root = args.data_root.resolve(strict=True) / "site-id"
    repo = args.repo.resolve(strict=True)
    try:
        import numpy  # noqa: F401
        import rasterio  # noqa: F401
    except ImportError as exc:
        parser.error(f"Python environment lacks processing dependencies: {exc}")

    completed = skipped = errors = 0
    for receipt in sorted(root.glob("*/flights/*/odm-submission.submitted.json")):
        folder = receipt.parent
        if args.flight_id and folder.name != args.flight_id:
            continue
        try:
            info = json.loads(receipt.read_text(encoding="utf-8"))
            if info.get("flight_id") != folder.name or info.get("organization_id") != folder.parent.parent.name:
                raise ValueError("Submission receipt does not match directory")
            snapshot = folder / "odm-slurm-accounting.json"
            if not snapshot.is_file():
                continue
            status = json.loads(snapshot.read_text(encoding="utf-8"))
            if (status.get("flight_id") != folder.name or
                    status.get("organization_id") != folder.parent.parent.name or
                    str(status.get("slurm_job_id")) != str(info.get("slurm_job_id"))):
                raise ValueError("Slurm accounting identity mismatch")
            if status.get("state") != "COMPLETED" or status.get("exit_code") != "0:0":
                continue
            orthophoto = folder / ORTHO
            if not nonempty(orthophoto):
                raise ValueError("Completed ODM job has no valid orthophoto")
            index_files = [folder / name for name in INDICES]
            existing = [p.exists() or p.is_symlink() for p in index_files]
            if any(existing) and not all(nonempty(p) for p in index_files):
                raise ValueError("Partial vegetation-index output requires operator review")
            if not any(existing):
                print(f"Generating VARI/GLI: {folder.name}", flush=True)
                subprocess.run([sys.executable,
                                str(repo / "ortho_processing/ortho_intelligence.py"),
                                str(orthophoto), str(folder / "odm")], check=True)
                if not all(nonempty(p) for p in index_files):
                    raise ValueError("Vegetation-index generation did not produce both TIFFs")
            if all(nonempty(folder / name) for name in PREVIEWS):
                skipped += 1
                print(f"CURRENT: {folder.name} indices and previews", flush=True)
                continue
            print(f"Generating previews: {folder.name}", flush=True)
            subprocess.run([sys.executable, str(repo / "scripts/generate-atlas-previews.py"),
                            folder.name, "--data-root", str(args.data_root)], check=True)
            if not all(nonempty(folder / name) for name in PREVIEWS):
                raise ValueError("Preview generation did not produce all three PNGs")
            completed += 1
            print(f"READY: {folder.name} all required products and previews", flush=True)
        except (OSError, ValueError, subprocess.CalledProcessError) as exc:
            errors += 1
            print(f"FAILED: {folder.name}: {exc}", file=sys.stderr, flush=True)
    print(f"Ceres postprocessing: {completed} completed; {skipped} already complete; {errors} errors", flush=True)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
