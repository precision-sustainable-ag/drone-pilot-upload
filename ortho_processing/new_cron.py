'''
Aimed as the orchestrator to send jobs using the DTN - trigger point
Jobs are sent using generate_ortho.sh
'''
import os
import shutil
import multiprocessing
import concurrent.futures
import logging
import json
from datetime import datetime, timedelta
import utils
from config import config
from services.scripts import write_odm_script, write_ortho_intel_script


# ---------- small helpers ----------

def _submit_and_monitor(script_path, flight_dir, flight_id, stage_name):
    """Submit LSF script and monitor it; return True if scheduler didn't immediately EXIT."""
    job_id = utils.lsfSubmitJob(script_path, flight_dir)
    logging.info({'service': 'processFlight',
                  'message': f'{flight_id} - {stage_name} job submitted - {job_id}'})
    status = utils.lsfMonitorJob(job_id, flight_id)
    # lsfMonitorJob returns 'EXIT' on immediate failure; anything else means it ran/finished/unknown.
    return status != 'EXIT'


def _finalize_outputs(flight_dir):
    """
    After successful ODM, move everything from ./code to flight root
    except 'images', then remove ./code if empty.
    """
    code_dir = os.path.join(flight_dir, 'code')
    if not os.path.isdir(code_dir):
        return
    for item in os.listdir(code_dir):
        if item == 'images':
            continue
        src = os.path.join(code_dir, item)
        dst = os.path.join(flight_dir, item)
        if os.path.exists(dst):
            # don't clobber existing, just keep it
            continue
        os.rename(src, dst)
    # remove ./code if only images remain (or empty)
    try:
        residual = [x for x in os.listdir(code_dir) if x != 'images']
        if not residual:
            shutil.rmtree(code_dir, ignore_errors=True)
    except FileNotFoundError:
        pass


def _odm_success(flight_dir):
    """
    Decide ODM success by artifacts (more robust than scheduler code):
    - code/log.json with {"success": true}, OR
    - presence of odm_orthophoto/odm_orthophoto.tif
    """
    # prefer explicit success in log.json
    for p in (os.path.join(flight_dir, 'code', 'log.json'),
              os.path.join(flight_dir, 'log.json')):
        try:
            with open(p, 'r') as f:
                j = json.load(f)
            if isinstance(j, dict) and j.get('success') is True:
                return True
        except Exception:
            pass
    # fall back to orthophoto existence
    ortho = os.path.join(flight_dir, 'odm_orthophoto', 'odm_orthophoto.tif')
    return os.path.isfile(ortho) and os.path.getsize(ortho) > 0


def _write_and_run_odm(flight_dir, flight_id):
    """Generate and run the ODM stage; return True if stage produced valid outputs."""
    odm_sif = os.path.join(config['code_dir'], 'sif_files', 'odm_gpu-fixed.sif')
    odm_script_path = os.path.join(flight_dir, 'odm_lsf.sh')
    write_odm_script(
        flight_dir=flight_dir,
        images_dir=os.path.join(flight_dir, 'images'),
        scratch_dir=config['scratch_dir'],
        odm_sif_file=odm_sif,
        script_path=odm_script_path,
        n_cores=32,
        wall="30:00",
        queue="gpu",
        mem_gb=250,
        pc_quality="medium",
    )

    ran_ok = _submit_and_monitor(odm_script_path, flight_dir, flight_id, 'odm')
    if not ran_ok:
        logging.error({'service': 'processFlight',
                       'message': f'{flight_id} - odm lsf failed'})
        return False

    # Check by artifacts, not scheduler code
    if not _odm_success(flight_dir):
        logging.error({'service': 'processFlight',
                       'message': f'{flight_id} - odm processing failed'})
        return False

    logging.info({'service': 'processFlight',
                  'message': f'{flight_id} - odm processing complete'})
    _finalize_outputs(flight_dir)
    return True


def _write_and_run_ortho_intel(flight_dir, flight_id):
    """Generate and run the ortho_intel stage; return True if it at least ran (scheduler not EXIT)."""
    ortho_file = os.path.join(flight_dir, 'odm_orthophoto', 'odm_orthophoto.tif')
    if not (os.path.isfile(ortho_file) and os.path.getsize(ortho_file) > 0):
        logging.error({'service': 'processFlight',
                       'message': f'{flight_id} - ortho file missing for ortho_intel'})
        return False

    oi_sif = os.path.join(config['code_dir'], 'sif_files', 'drone_ortho_intel.sif')
    oi_script_path = os.path.join(flight_dir, 'ortho_intel_lsf.sh')
    write_ortho_intel_script(
        flight_dir=flight_dir,
        scratch_dir=config['scratch_dir'],
        ortho_intel_sif_file=oi_sif,
        ortho_file=ortho_file,
        script_path=oi_script_path,
        n_cores=32,
        wall="2:00",
        queue="short",
    )

    ran_ok = _submit_and_monitor(oi_script_path, flight_dir, flight_id, 'ortho intel')
    if not ran_ok:
        logging.error({'service': 'processFlight',
                       'message': f'{flight_id} - ortho intel lsf failed'})
        return False

    logging.info({'service': 'processFlight',
                  'message': f'{flight_id} - ortho intel processing complete'})
    return True


# ---------- main per-flight logic ----------

def processFlight(flight_id):
    client, db_collection = utils.connectDb()
    meta = db_collection.find({'flight_id': flight_id})[0]
    research_station = meta['research_station']
    status = meta.get('status')
    flight_dir = os.path.join(config['mount_dir'], research_station, 'flights', flight_id)

    # Sanity: image count must match
    images_dir = os.path.join(flight_dir, 'images')
    if meta['num_files'] != utils.countFiles(images_dir):
        logging.info({'service': 'processFlight',
                      'message': f'{flight_id} - file count not matching'})
        return None

    # --- NEW: If already "ortho generated", skip ODM and run ONLY ortho_intel ---
    if status == 'ortho generated':
        logging.info({'service': 'processFlight',
                      'message': f'{flight_id} - status=ortho generated, skipping ODM'})
        if _write_and_run_ortho_intel(flight_dir, flight_id):
            utils.updateRecord(flight_dir, flight_id, 'processed', research_station)
            return flight_id
        else:
            utils.updateRecord(flight_dir, flight_id, 'failed')
            return None

    # Default path: run ODM then ortho_intel
    utils.updateRecord(flight_dir, flight_id, 'processing')

    if not _write_and_run_odm(flight_dir, flight_id):
        utils.updateRecord(flight_dir, flight_id, 'failed')
        return None

    utils.updateRecord(flight_dir, flight_id, 'ortho generated')

    if _write_and_run_ortho_intel(flight_dir, flight_id):
        utils.updateRecord(flight_dir, flight_id, 'processed', research_station)
        return flight_id
    else:
        utils.updateRecord(flight_dir, flight_id, 'failed')
        return None


def main():
    # gets all flights uploaded yesterday (and earlier) for central
    client, db_collection = utils.connectDb()
    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday = datetime.combine(yesterday, datetime.min.time())

    query = {"upload_time": {"$lt": yesterday}, "research_station": "central"}
    results = db_collection.find(query)

    records_to_process = []
    for row in results:
        # always allow 'ortho generated' so we can finish them
        if 'status' not in row:
            records_to_process.append(row['flight_id'])
        elif row['status'] in ['processed', 'processing']:
            # Skip already processed and currently-running
            continue
        else:
            # includes: ortho generated, failed, unknown, etc.
            records_to_process.append(row['flight_id'])

    if records_to_process:
        logging.info({'service': 'database query', 'message': records_to_process})
        num_workers = multiprocessing.cpu_count()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            executor.map(processFlight, records_to_process)
    else:
        logging.info({'service': 'database query', 'message': 'no records'})


if __name__ == '__main__':
    utils.setup_logging()
    main()
