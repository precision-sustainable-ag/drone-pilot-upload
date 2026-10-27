import os
import subprocess
import sys

from config import config
from services.db import connect_db

SRC_STATION = "sandhills"
DST_STATION = "umstead"
DRY_RUN = False  # <-- set to False to actually move+symlink


def shell(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    if not DRY_RUN:
        subprocess.run(cmd, check=True)


def main():
    _, coll = connect_db()
    docs = list(coll.find({"research_station": SRC_STATION, "status": "processed"}))
    if not docs:
        print("No failed flights found for sandhills.")
        return

    print(f"Found {len(docs)} failed flights in {SRC_STATION} to relocate.\n")

    i = 0
    limit = 10

    for d in docs:
        fid = d.get("flight_id")
        if not fid:
            continue

        src = os.path.join(config["mount_dir"], SRC_STATION, "flights", fid)
        dst = os.path.join(config["mount_dir"], DST_STATION, "flights", fid)

        # sanity checks
        if not os.path.exists(src):
            print(f"!! SKIP {fid}: source does not exist: {src}", file=sys.stderr)
            continue
        if os.path.islink(src):
            print(f"-- SKIP {fid}: source is already a symlink: {src}")
            continue
        if os.path.exists(dst):
            print(f"!! SKIP {fid}: destination already exists: {dst}", file=sys.stderr)
            continue

        if not DRY_RUN:
            os.makedirs(os.path.dirname(dst), exist_ok=True)

        # rsync preserves perms/times, handles cross-filesystems cleanly
        shell(["rsync", "-a", "--info=progress2", f"{src}/", dst])

        # remove the original tree and replace with a symlink to the new location
        shell(["rm", "-rf", src])
        shell(["ln", "-s", dst, src])
        print(f"OK  {fid}: moved -> {dst} and linked back -> {src}\n")
        if i >= limit:
            break

        i += 1
    if DRY_RUN:
        print("DRY_RUN=True: no changes made. Set DRY_RUN=False to execute.")
    else:
        print("Done.")


if __name__ == "__main__":
    main()
