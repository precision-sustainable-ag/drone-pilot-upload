import os

from services.artifacts import finalize_outputs, odm_done
from services.logs import get_logger
from services.lsf import monitor, submit
from services.scripts import write_odm_script, write_ortho_intel_script  # you already have this

# setup logging
log = get_logger(__name__, component="pipeline")


def submit_and_monitor(script_path: str, flight_dir: str, flight_id: str, stage_name: str) -> bool:
    job_id = submit(script_path, flight_dir)
    log.info({"event": "lsf_submit", "flight_id": flight_id, "stage": stage_name, "job_id": job_id})
    if job_id is None:
        return False
    status = monitor(job_id)
    log.info(
        {
            "event": "lsf_status",
            "flight_id": flight_id,
            "stage": stage_name,
            "job_id": job_id,
            "status": status,
        }
    )
    return status != "EXIT"


def write_and_run_odm(flight_dir: str, flight_id: str) -> bool:
    script_path = os.path.join(flight_dir, "odm_lsf.sh")
    write_odm_script(
        flight_dir=flight_dir,
        images_dir=os.path.join(flight_dir, "images"),
        script_path=script_path,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, "odm"):
        log.error({"event": "odm_lsf_failed", "flight_id": flight_id})
        return False
    ok, _ = odm_done(flight_dir)
    if not ok:
        log.error({"event": "odm_artifacts_missing", "flight_id": flight_id})
        return False
    log.info({"event": "odm_complete", "flight_id": flight_id})
    finalize_outputs(flight_dir)
    return True


def write_and_run_ortho_intel(flight_dir: str, flight_id: str) -> bool:
    ortho_file = os.path.join(flight_dir, "odm_orthophoto", "odm_orthophoto.tif")
    if not (os.path.isfile(ortho_file) and os.path.getsize(ortho_file) > 0):
        log.error(
            {"event": "ortho_intel_missing_input", "flight_id": flight_id, "path": ortho_file}
        )
        return False
    script_path = os.path.join(flight_dir, "ortho_intel_lsf.sh")
    write_ortho_intel_script(
        flight_dir=flight_dir,
        ortho_file=ortho_file,
        script_path=script_path,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, "ortho intel"):
        log.error({"event": "ortho_intel_lsf_failed", "flight_id": flight_id})
        return False
    log.info({"event": "ortho_intel_complete", "flight_id": flight_id})
    return True
