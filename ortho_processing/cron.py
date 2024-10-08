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


def generateLsfScript(flight_dir, flight_id, process_name, ortho_file=None):
    if process_name == 'odm':
        odm_sif_file = os.path.join(config['code_dir'], 'sif_files',
                                    'odm_gpu.sif')
        lsfScript = os.path.join(flight_dir, 'odm_lsf.sh')
        with open(lsfScript, 'w') as file:
            file.write(f"""#!/bin/bash
        #BSUB -n 32
        ## requested job run time
        #BSUB -W 30:00
        #BSUB -q gpu
        #BSUB -R "select[ a100 || a10 || a30 ]"
        #BSUB -gpu "num=1:mode=shared:mps=no"
        ## Tag general output file and std error output
        #BSUB -o odm_processing-out.txt
        #BSUB -e odm_processing-err.txt
        export tmp_dir='{config['scratch_dir']}'
        export output_dir='{flight_dir}'
        export images_dir='{os.path.join(flight_dir, 'images')}'
        mkdir -p $output_dir/code/images
        cp $images_dir/* $output_dir/code/images
        cd $output_dir
        singularity run --bind $output_dir/code/images,$tmp_dir \
        --writable-tmpfs --nv {odm_sif_file} --project-path $output_dir \
        --dtm --orthophoto-resolution 0.01 --smrf-threshold 0.4 \
        --smrf-window 24 --dsm --feature-quality ultra --min-num-features 50000
        """)

    elif process_name == 'ortho_intel':
        lsfScript = os.path.join(flight_dir, 'ortho_intel_lsf.sh')
        ortho_intel_sif_file = os.path.join(config['code_dir'], 'sif_files',
                                            'drone_ortho_intel.sif')
        with open(lsfScript, 'w') as file:
            file.write(f"""#!/bin/bash
        #BSUB -n 32
        ## requested job run time
        #BSUB -W 5:00
        #BSUB -q sif
        #BSUB -R "select[avx2]"
        ## Tag general output file and std error output
        #BSUB -o ortho_intel-out.txt
        #BSUB -e ortho_intel-err.txt
        export tmp_dir={config['scratch_dir']}
        export flight_dir={flight_dir}
        export ortho_file={ortho_file}
        cd $flight_dir
        singularity run --bind $flight_dir,$tmp_dir --writable-tmpfs \
        {ortho_intel_sif_file} $ortho_file $flight_dir""")
    else:
        lsfScript = None
    return lsfScript


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
    if flight_metadata['num_files'] == utils.countFiles(flight_dir):
        odm_script = generateLsfScript(flight_dir, flight_id, 'odm')
        utils.updateRecord(flight_dir, flight_id, 'processing')
        job_id = utils.lsfSubmitJob(odm_script, flight_dir)
        logging.info({
            'service': 'processFlight',
            'message': f'{flight_id} - odm job submitted - {job_id}'
        })
        status = utils.lsfMonitorJob(job_id, flight_id)
        if status != 'EXIT':
            code_dir = os.path.join(flight_dir, 'code')
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
                for item in os.listdir(code_dir):
                    item_path = os.path.join(code_dir, item)
                    if item != 'images':
                        dest_path = os.path.join(flight_dir, item)
                        os.rename(item_path, dest_path)
                shutil.rmtree(code_dir)
                utils.updateRecord(flight_dir, flight_id, 'ortho generated')
                ortho_file = os.path.join(flight_dir, 'odm_orthophoto',
                                          'odm_orthophoto.tif')
                ortho_intel_script = generateLsfScript(flight_dir, flight_id,
                                                       'ortho_intel',
                                                       ortho_file)
                job_id = utils.lsfSubmitJob(ortho_intel_script, flight_dir)
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
    query = {"upload_time": {"$gte": yesterday, "$lt": today}}

    results = db_collection.find(query)
    records_to_process = []
    for row in results:
        if 'status' not in row.keys():
            records_to_process.append(row['flight_id'])
        elif row['status'] not in ['processed', 'processing', 'failed',
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
