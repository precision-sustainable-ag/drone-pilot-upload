import os
import shutil
from config import config

def count_files(path: str) -> int:
    try:
        return sum(1 for e in os.scandir(path) if e.is_file())
    except FileNotFoundError:
        return 0

def exists_nonempty(path: str) -> bool:
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False

def dir_exists_nonempty(path: str) -> bool:
    try:
        return os.path.isdir(path) and any(os.scandir(path))
    except OSError:
        return False

def safe_move_tree(src: str, dst: str) -> None:
    if not os.path.exists(src):
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        os.rename(src, dst)
    except OSError:
        shutil.copytree(src, dst, dirs_exist_ok=True)
        shutil.rmtree(src, ignore_errors=True)

def flight_dir_for(meta):
    """Resolve flight directory from metadata."""
    rs = meta["research_station"]
    fid = meta["flight_id"]
    return os.path.join(config["mount_dir"], rs, "flights", fid)
