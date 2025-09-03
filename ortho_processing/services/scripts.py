from __future__ import annotations
import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=(), default_for_string=False),
    trim_blocks=True,
    lstrip_blocks=True,
)

def _render(template_name: str, **ctx) -> str:
    tpl = _env.get_template(template_name)
    return tpl.render(**ctx)

def write_odm_script(*, flight_dir: str, images_dir: str, scratch_dir: str,
                     odm_sif_file: str, script_path: str,
                     n_cores: int = 32, wall: str = "30:00", queue: str = "gpu",
                     mem_gb: int = 250, gpu_num: int = 1, gmodel: str | None = None, pc_quality: str = "medium") -> str:
    """Render and write the ODM LSF script; return the path written."""
    content = _render(
        "odm_lsf.sh.j2",
        n_cores=n_cores,
        wall=wall,
        queue=queue,
        mem_gb=mem_gb,
        scratch_dir=scratch_dir,
        flight_dir=flight_dir,
        images_dir=images_dir,
        odm_sif_file=odm_sif_file,
        pc_quality=pc_quality,
    )
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    return script_path

def write_ortho_intel_script(*, flight_dir: str, scratch_dir: str,
                             ortho_intel_sif_file: str, ortho_file: str,
                             script_path: str, n_cores: int = 32, wall: str = "5:00",
                             queue: str = "short") -> str:
    """Render and write the ortho_intel LSF script; return the path written."""
    content = _render(
        "ortho_intel_lsf.sh.j2",
        n_cores=n_cores,
        wall=wall,
        queue=queue,
        scratch_dir=scratch_dir,
        flight_dir=flight_dir,
        ortho_file=ortho_file,
        ortho_intel_sif_file=ortho_intel_sif_file,
    )
    os.makedirs(os.path.dirname(script_path), exist_ok=True)
    with open(script_path, "w") as f:
        f.write(content)
    os.chmod(script_path, 0o755)
    return script_path
