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
import os


def processFlight(flight_id):
    # TODO: get record metadata before and get research station to complete
    #  flight_dir
    client, db_collection = utils.connectDb()
    query = {'flight_id': flight_id}
    flight_metadata = db_collection.find(query)[0]
    research_station = flight_metadata['research_station']
    flight_dir = os.path.join(config['mount_dir'], research_station, 'flights',
                              flight_id)
    # flight_dir = os.path.join(config['flights_dir'], flight_id)
    if flight_metadata['num_files'] == utils.countFiles(os.path.join(flight_dir,'images')):
        utils.updateRecord(flight_dir, flight_id, 'processing')

        # write the odm script to flight dir
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

        job_id = utils.lsfSubmitJob(odm_script_path, flight_dir)
        logging.info({
            'service': 'processFlight',
            'message': f'{flight_id} - odm job submitted - {job_id}'
        })
        status = utils.lsfMonitorJob(job_id, flight_id)
        if status != 'EXIT':
            code_dir = os.path.join(flight_dir, 'code')
            # TODO: update this to read the actual status from log
            # fails when HPC times out and status is not exit
            # read to correctly mark pass/failed
            if not os.path.exists(os.path.join(code_dir, 'log.json')):
                logging.error({
                    'service': 'processFlight',
                    'message': f'{flight_id} - odm log file not there'
                })
                utils.updateRecord(flight_dir, flight_id, 'failed')
                return None
            with open(os.path.join(code_dir, 'log.json'), 'r') as log_file:
                log_json = json.loads(log_file.read())
                status = log_json['success']
                if not status:
                    logging.error({
                        'service': 'processFlight',
                        'message': f'{flight_id} - odm processing failed'
                    })
                    utils.updateRecord(flight_dir, flight_id, 'failed')
                    return None

                logging.info({
                    'service': 'processFlight',
                    'message': f'{flight_id} - odm processing complete'
                })
                # jobEndTime = parseJsonLogFile("endTime", flight_dir)
                # jobTotalTime = parseJsonLogFile("totalTime", flight_dir)
                # TODO: L117-123 - some 'code' folders aren't being deleted
                for item in os.listdir(code_dir):
                    item_path = os.path.join(code_dir, item)
                    if item != 'images':
                        dest_path = os.path.join(flight_dir, item)
                        os.rename(item_path, dest_path)
                shutil.rmtree(code_dir)
                utils.updateRecord(flight_dir, flight_id, 'ortho generated')

                # generate ortho sif script
                oi_sif = os.path.join(config['code_dir'], 'sif_files', 'drone_ortho_intel.sif')
                oi_script_path = os.path.join(flight_dir, 'ortho_intel_lsf.sh')
                ortho_file = os.path.join(flight_dir, 'odm_orthophoto', 'odm_orthophoto.tif')
                write_ortho_intel_script(
                    flight_dir=flight_dir,
                    scratch_dir=config['scratch_dir'],
                    ortho_intel_sif_file=oi_sif,
                    ortho_file=ortho_file,
                    script_path=oi_script_path,
                    n_cores=32,
                    wall="5:00",
                    queue="short",
                )

                job_id = utils.lsfSubmitJob(oi_script_path, flight_dir)
                logging.info({
                    'service': 'processFlight',
                    'message': f'{flight_id} - ortho intel job submitted -'
                               f' {job_id}'
                })
                status = utils.lsfMonitorJob(job_id, flight_id)
                if status != 'EXIT':
                    # TODO: @jinam - this might fail too incase there is error
                    #  in code
                    logging.info({
                        'service': 'processFlight',
                        'message': f'{flight_id} - ortho intel processing '
                                   f'complete'
                    })
                    utils.updateRecord(flight_dir, flight_id, 'processed',
                                       research_station)
                    return flight_id
                else:
                    logging.error({
                        'service': 'processFlight',
                        'message': f'{flight_id} - ortho intel lsf failed'
                    })
                    utils.updateRecord(flight_dir, flight_id, 'failed')
                    return None
        else:
            logging.error({
                'service': 'processFlight',
                'message': f'{flight_id} - odm lsf failed'
            })
            utils.updateRecord(flight_dir, flight_id, 'failed')
            return None
    else:
        logging.info({
            'service': 'processFlight',
            'message': f'{flight_id} - file count not matching'
        })
        return None


def main():
    # gets all flights uploaded yesterday
    client, db_collection = utils.connectDb()
    yesterday = (datetime.now() - timedelta(days=1)).date()
    today = datetime.now().date()
    # adding midnight as hour,min,sec (full datetime object is needed for mongo)
    yesterday = datetime.combine(yesterday, datetime.min.time())
    today = datetime.combine(today, datetime.min.time())
    query = {"upload_time": {"$lt": yesterday}, "research_station": "central"}

    results = db_collection.find(query)
    records_to_process = []
    for row in results:
        if 'status' not in row.keys():
            records_to_process.append(row['flight_id'])
        elif row['status'] not in ['processed', 'processing',
                                   'ortho generated']:
            records_to_process.append(row['flight_id'])
    if len(records_to_process) > 0:
        logging.info({
            'service': 'database query',
            'message': records_to_process
        })
        num_workers = multiprocessing.cpu_count()
        # with concurrent.futures.ThreadPoolExecutor(
        #         max_workers=num_workers) as executor:
        #     executor.map(trigger, records_to_process)
        with concurrent.futures.ThreadPoolExecutor(
                max_workers=num_workers) as executor:
            executor.map(processFlight, records_to_process)
    else:
        logging.info({
            'service': 'database query',
            'message': 'no records'
        })


if __name__ == '__main__':
    utils.setup_logging()
    main()
