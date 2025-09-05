'''
Aimed as the orchestrator to send jobs using the DTN - trigger point
Jobs are sent using generate_ortho.sh
'''
import os
import multiprocessing
import concurrent.futures
import logging
import itertools
from datetime import datetime, timedelta
from config import config
from services.pipeline import write_and_run_odm, write_and_run_ortho_intel
from services.fs import count_files
from services.db import connect_db
from services.logs import setup_logging
from services.persistence import update_record
from reconcile_flights import reconcile_one

# ---------- main per-flight logic ----------

def processFlight(flight_id, db_collection=None):
    # Allow single-flight testing without main(): connect if not provided
    if db_collection is None:
        _, db_collection = connect_db()

    meta = db_collection.find_one({'flight_id': flight_id})
    if not meta:
        logging.error({'service': 'processFlight', 'message': f'{flight_id} - no DB record found'})
        return None

    # targeted reconcile first (freshen stage/overall; moves outputs if ODM done)
    try:
        reconcile_one(db_collection, meta, dry_run=False, finalize=True)
        # refresh after reconcile
        meta = db_collection.find_one({'flight_id': flight_id}) or meta
    except Exception as e:
        logging.exception("reconcile before processing failed for %s: %s", flight_id, e)

    research_station = meta['research_station']
    status = meta.get('status')
    flight_dir = os.path.join(config['mount_dir'], research_station, 'flights', flight_id)

    # Sanity: image count must match
    images_dir = os.path.join(flight_dir, 'images')
    if meta['num_files'] != count_files(images_dir):
        logging.info({'service': 'processFlight',
                      'message': f'{flight_id} - file count not matching'})
        return None

    # --- NEW: If already "ortho generated", skip ODM and run ONLY ortho_intel ---
    if status == 'ortho generated':
        logging.info({'service': 'processFlight',
                      'message': f'{flight_id} - status=ortho generated, skipping ODM'})
        if write_and_run_ortho_intel(flight_dir, flight_id):
            update_record(flight_dir, flight_id, 'processed', research_station)
            return flight_id
        else:
            update_record(flight_dir, flight_id, 'failed')
            return None

    # Default path: run ODM then ortho_intel
    update_record(flight_dir, flight_id, 'processing')

    if not write_and_run_odm(flight_dir, flight_id):
        update_record(flight_dir, flight_id, 'failed')
        return None

    update_record(flight_dir, flight_id, 'ortho generated')

    if write_and_run_ortho_intel(flight_dir, flight_id):
        update_record(flight_dir, flight_id, 'processed', research_station)
        return flight_id
    else:
        update_record(flight_dir, flight_id, 'failed')
        return None


def main():
    # setup loigging from config file
    setup_logging()

    # use global db collection
    client, db_collection = connect_db()

    # gets all flights uploaded yesterday (and earlier) for central
    yesterday = (datetime.now() - timedelta(days=1)).date()
    yesterday = datetime.combine(yesterday, datetime.min.time())

    query = {"upload_time": {"$lt": yesterday}, "research_station": "central"}
    results = db_collection.find(query)

    records_to_process = []
    for row in results:
        # always allow 'ortho generated' so we can finish them
        if 'status' not in row:
            records_to_process.append(row['flight_id'])
        elif row['status'] in ['processed', 'processing', 'failed']:
            # Skip already processed and currently-running
            continue
        else:
            # includes: ortho generated, failed, unknown, etc.
            records_to_process.append(row['flight_id'])

    if records_to_process:
        logging.info({'service': 'database query', 'message': records_to_process})
        num_workers = multiprocessing.cpu_count()
        with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
            executor.map(processFlight, records_to_process, itertools.repeat(db_collection))
    else:
        logging.info({'service': 'database query', 'message': 'no records'})


if __name__ == '__main__':
    main()
