import logging
import os

from services.lsf import monitor, submit
from services.scripts import write_odm_script, write_ortho_intel_script  # you already have this

from .artifacts import finalize_outputs, odm_done


def submit_and_monitor(script_path: str, flight_dir: str, flight_id: str, stage_name: str) -> bool:
    job_id = submit(script_path, flight_dir)
    logging.info(
        {
            "service": "processFlight",
            "message": f"{flight_id} - {stage_name} job submitted - {job_id}",
        }
    )
    if job_id is None:
        return False
    status = monitor(job_id)
    return status != "EXIT"


def write_and_run_odm(flight_dir: str, flight_id: str) -> bool:
    script_path = os.path.join(flight_dir, "odm_lsf.sh")
    write_odm_script(
        flight_dir=flight_dir,
        images_dir=os.path.join(flight_dir, "images"),
        script_path=script_path,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, "odm"):
        logging.error({"service": "processFlight", "message": f"{flight_id} - odm lsf failed"})
        return False
    ok, _ = odm_done(flight_dir)
    if not ok:
        logging.error(
            {"service": "processFlight", "message": f"{flight_id} - odm processing failed"}
        )
        return False
    logging.info({"service": "processFlight", "message": f"{flight_id} - odm processing complete"})
    finalize_outputs(flight_dir)
    return True


def write_and_run_ortho_intel(flight_dir: str, flight_id: str) -> bool:
    ortho_file = os.path.join(flight_dir, "odm_orthophoto", "odm_orthophoto.tif")
    if not (os.path.isfile(ortho_file) and os.path.getsize(ortho_file) > 0):
        logging.error(
            {
                "service": "processFlight",
                "message": f"{flight_id} - ortho file missing for ortho_intel",
            }
        )
        return False
    script_path = os.path.join(flight_dir, "ortho_intel_lsf.sh")
    write_ortho_intel_script(
        flight_dir=flight_dir,
        ortho_file=ortho_file,
        script_path=script_path,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, "ortho intel"):
        logging.error(
            {"service": "processFlight", "message": f"{flight_id} - ortho intel lsf failed"}
        )
        return False
    logging.info(
        {"service": "processFlight", "message": f"{flight_id} - ortho intel processing complete"}
    )
    return True
