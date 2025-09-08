from __future__ import annotations

import os

from config import config
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.logs import get_logger

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

# setup logging
log = get_logger(__name__, component="scripts")

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=(), default_for_string=False),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _render(template_name: str, **ctx) -> str:
    tpl = _env.get_template(template_name)
    return tpl.render(**ctx)


def write_odm_script(*, flight_dir: str, images_dir: str, script_path: str) -> str:
    """Render and write the ODM LSF script; return the path written."""
    odm_cfg = config["odm"]
    odm_sif_file = os.path.join(config["code_dir"], odm_cfg["sif_file"])
    content = _render(
        "odm_lsf.sh.j2",
        n_cores=odm_cfg["n_cores"],
        wall=odm_cfg["wall"],
        queue=odm_cfg["queue"],
        mem_gb=odm_cfg["mem_gb"],
        scratch_dir=config["scratch_dir"],
        flight_dir=flight_dir,
        images_dir=images_dir,
        odm_sif_file=odm_sif_file,
        pc_quality=odm_cfg["pc_quality"],
    )
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)

    log.debug(
        {
            "event": "write_script",
            "kind": "odm",
            "script_path": script_path,
            "flight_dir": flight_dir,
            "images_dir": images_dir,
            "queue": odm_cfg["queue"],
            "n_cores": odm_cfg["n_cores"],
            "wall": odm_cfg["wall"],
            "mem_gb": odm_cfg["mem_gb"],
            "pc_quality": odm_cfg["pc_quality"],
        }
    )

    return script_path


def write_ortho_intel_script(*, flight_dir: str, ortho_file: str, script_path: str) -> str:
    """Render and write the ortho_intel LSF script; return the path written."""
    oi_cfg = config["ortho_intel"]
    ortho_intel_sif_file = os.path.join(config["code_dir"], oi_cfg["sif_file"])
    content = _render(
        "ortho_intel_lsf.sh.j2",
        n_cores=oi_cfg["n_cores"],
        wall=oi_cfg["wall"],
        queue=oi_cfg["queue"],
        scratch_dir=config["scratch_dir"],
        flight_dir=flight_dir,
        ortho_file=ortho_file,
        ortho_intel_sif_file=ortho_intel_sif_file,
    )
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)

    log.debug(
        {
            "event": "write_script",
            "kind": "ortho_intel",
            "script_path": script_path,
            "flight_dir": flight_dir,
            "ortho_file": ortho_file,
            "queue": oi_cfg["queue"],
            "n_cores": oi_cfg["n_cores"],
            "wall": oi_cfg["wall"],
        }
    )

    return script_path
