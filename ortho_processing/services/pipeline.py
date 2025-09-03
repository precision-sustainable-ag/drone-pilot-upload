import os
import logging
from config import config
import utils
from .artifacts import odm_done, finalize_outputs
from services.scripts import write_odm_script, write_ortho_intel_script  # you already have this

def submit_and_monitor(script_path: str, flight_dir: str, flight_id: str, stage_name: str) -> bool:
    job_id = utils.lsfSubmitJob(script_path, flight_dir)
    logging.info({'service': 'processFlight', 'message': f'{flight_id} - {stage_name} job submitted - {job_id}'})
    status = utils.lsfMonitorJob(job_id, flight_id)
    return status != 'EXIT'

def write_and_run_odm(flight_dir: str, flight_id: str,
                      n_cores=32, wall="30:00", queue="gpu", mem_gb=250, pc_quality="medium") -> bool:
    odm_sif = os.path.join(config['code_dir'], 'sif_files', 'odm_gpu-fixed.sif')
    script_path = os.path.join(flight_dir, 'odm_lsf.sh')
    write_odm_script(
        flight_dir=flight_dir,
        images_dir=os.path.join(flight_dir, 'images'),
        scratch_dir=config['scratch_dir'],
        odm_sif_file=odm_sif,
        script_path=script_path,
        n_cores=n_cores,
        wall=wall,
        queue=queue,
        mem_gb=mem_gb,
        pc_quality=pc_quality,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, 'odm'):
        logging.error({'service': 'processFlight', 'message': f'{flight_id} - odm lsf failed'})
        return False
    ok, _ = odm_done(flight_dir)
    if not ok:
        logging.error({'service': 'processFlight', 'message': f'{flight_id} - odm processing failed'})
        return False
    logging.info({'service': 'processFlight', 'message': f'{flight_id} - odm processing complete'})
    finalize_outputs(flight_dir)
    return True

def write_and_run_ortho_intel(flight_dir: str, flight_id: str,
                              n_cores=32, wall="5:00", queue="short") -> bool:
    ortho_file = os.path.join(flight_dir, 'odm_orthophoto', 'odm_orthophoto.tif')
    if not (os.path.isfile(ortho_file) and os.path.getsize(ortho_file) > 0):
        logging.error({'service': 'processFlight', 'message': f'{flight_id} - ortho file missing for ortho_intel'})
        return False
    oi_sif = os.path.join(config['code_dir'], 'sif_files', 'drone_ortho_intel.sif')
    script_path = os.path.join(flight_dir, 'ortho_intel_lsf.sh')
    write_ortho_intel_script(
        flight_dir=flight_dir,
        scratch_dir=config['scratch_dir'],
        ortho_intel_sif_file=oi_sif,
        ortho_file=ortho_file,
        script_path=script_path,
        n_cores=n_cores,
        wall=wall,
        queue=queue,
    )
    if not submit_and_monitor(script_path, flight_dir, flight_id, 'ortho intel'):
        logging.error({'service': 'processFlight', 'message': f'{flight_id} - ortho intel lsf failed'})
        return False
    logging.info({'service': 'processFlight', 'message': f'{flight_id} - ortho intel processing complete'})
    return True
