#!/usr/bin/env python3
"""Generate missing Atlas flight previews after successful ODM processing."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_ROOT = Path(os.environ.get(
    "DPU_DATA_ROOT",
    "/project/dash_drone/user/stephen.amerige/dpu-data"
))
PREVIEWS = ("orthophoto.png", "vari.png", "gli.png")


def main():
    root = DATA_ROOT / "site-id"
    if not root.is_dir():
        print(f"Flight storage unavailable: {root}", file=sys.stderr)
        return 1

    generated = skipped = failures = 0

    for receipt in sorted(root.glob(
        "*/flights/*/odm-submission.submitted.json"
    )):
        flight_dir = receipt.parent
        snapshot = flight_dir / "odm-slurm-accounting.json"

        if not snapshot.is_file():
            continue

        try:
            status = json.loads(snapshot.read_text(encoding="utf-8"))
            if (
                status.get("state") != "COMPLETED"
                or status.get("exit_code") != "0:0"
            ):
                continue

            preview_dir = flight_dir / "previews"
            if all(
                (preview_dir / name).is_file()
                and (preview_dir / name).stat().st_size > 0
                for name in PREVIEWS
            ):
                skipped += 1
                continue

            print(f"Generating missing previews: {flight_dir.name}", flush=True)

            result = subprocess.run(
                ["bash", str(SCRIPT_DIR / "atlas.sh"),
                 "preview", flight_dir.name],
                check=False,
            )
            if result.returncode:
                failures += 1
                print(f"Preview generation failed: {flight_dir.name}",
                      file=sys.stderr)
            else:
                generated += 1

        except (OSError, ValueError) as exc:
            failures += 1
            print(f"Preview check failed: {flight_dir.name}: {exc}",
                  file=sys.stderr)

    print(
        f"Previews: {generated} generated, "
        f"{skipped} already complete, {failures} errors",
        flush=True,
    )
    return int(bool(failures))


if __name__ == "__main__":
    sys.exit(main())
