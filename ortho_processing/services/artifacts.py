import os
import json
import logging
from .fs import exists_nonempty, dir_exists_nonempty, safe_move_tree

def load_json(path: str):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return None

def has_orthophoto(fdir: str) -> str|None:
    p1 = os.path.join(fdir, "odm_orthophoto", "odm_orthophoto.tif")
    p2 = os.path.join(fdir, "code", "odm_orthophoto", "odm_orthophoto.tif")
    if exists_nonempty(p1):
        return p1
    if exists_nonempty(p2):
        return p2
    return None

def odm_done(fdir: str) -> tuple[bool, str]:
    for cand in (os.path.join(fdir, "code", "log.json"),
                 os.path.join(fdir, "log.json")):
        j = load_json(cand)
        if isinstance(j, dict) and j.get("success") is True:
            return True, f"log.json success=true ({os.path.relpath(cand, fdir)})"
    ortho = has_orthophoto(fdir)
    if ortho:
        return True, f"orthophoto present ({os.path.relpath(ortho, fdir)})"
    return False, "no success markers and no orthophoto"

def ortho_intel_done(fdir: str) -> tuple[bool, str]:
    veg_dir = os.path.join(fdir, "veg_indices")
    if os.path.isdir(veg_dir):
        for name in os.listdir(veg_dir):
            if name.lower().endswith((".tif", ".tiff", ".png")):
                p = os.path.join(veg_dir, name)
                if exists_nonempty(p):
                    return True, f"veg_indices raster present ({name})"
    # diagnostics only
    cog = os.path.join(fdir, "odm_orthophoto", "odm_orthophoto_cog.tif")
    if exists_nonempty(cog):
        return False, "COG present but no veg indices rasters"
    return False, "no ortho_intel artifacts"

def finalize_outputs(fdir: str, dry_run: bool=False) -> None:
    code_dir = os.path.join(fdir, "code")
    if not os.path.isdir(code_dir):
        return
    for item in os.listdir(code_dir):
        if item == "images":
            continue
        src = os.path.join(code_dir, item)
        dst = os.path.join(fdir, item)
        if os.path.exists(dst):
            logging.debug("finalize: destination exists, skipping %s", os.path.relpath(dst, fdir))
            continue
        if not dry_run:
            safe_move_tree(src, dst)
    try:
        residual = [x.name for x in os.scandir(code_dir) if x.name != "images"]
        if not residual:
            if not dry_run:
                import shutil
                shutil.rmtree(code_dir, ignore_errors=True)
    except FileNotFoundError:
        pass
