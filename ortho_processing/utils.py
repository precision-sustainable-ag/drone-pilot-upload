'''
This script serves two functions:
1. Has helper code for cron.py
2. Has update_ortho code that is triggered if the script is called directly
instead of importing - this communicates with db and is the only part
responsible for inserts/updates into the database
'''

import os
import subprocess
import pyproj
import pymongo
import logging
from logging.handlers import TimedRotatingFileHandler
from config import config


def setup_logging():
    log_file = config['log_file']
    log_folder = os.path.split(log_file)[0]
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)
    file_handler = TimedRotatingFileHandler(log_file, when='D', interval=30)

    # Set the log level and formatter
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    # Add the file handler to the root logger
    logging.getLogger().setLevel(logging.INFO)
    logging.getLogger().addHandler(file_handler)


def readCRS(flight_dir):
    crs_file = os.path.join(flight_dir, 'odm_georeferencing', 'proj.txt')
    with open(crs_file, 'r') as file:
        crs_string = file.readline()
    return f'EPSG:{(pyproj.CRS.from_string(crs_string)).to_epsg()}'


def connectDb():
    database_details = config['database_details']
    client = pymongo.MongoClient(database_details['connection_string'])
    collection = client[database_details['database']][database_details[
        'collection']]
    return client, collection


def updateRecord(flight_dir, flight_id, status, research_station='virtual'):
    """
    The research_station parameter is only used when status is processed hence
    the default value to avoid passing the variable in all updateRecord calls.
    """
    try:
        if status == 'processed':
            source_crs = readCRS(flight_dir)

            orthophoto_path = os.path.join(research_station, 'flights',
                                           flight_id, 'odm_orthophoto',
                                           'odm_orthophoto.tif')
            cog_path = os.path.join(research_station, 'flights', flight_id,
                                    'odm_orthophoto', 'odm_orthophoto_cog.tif')
            veg_index_folder = os.path.join(research_station, 'flights',
                                            flight_id, 'veg_indices')

            query = {'flight_id': flight_id}
            update = {"$set": {
                "orthophoto_path": orthophoto_path,
                "cog_path": cog_path,
                "orthophoto_source_crs": source_crs,
                "veg_index_folder": veg_index_folder,
                "status": "processed"
            }}

            client, db_collection = connectDb()
            db_collection.update_one(query, update, upsert=True)
        elif status == 'ortho generated':
            source_crs = readCRS(flight_dir)
            orthophoto_path = os.path.join(research_station, 'flights',
                                           flight_id, 'odm_orthophoto',
                                           'odm_orthophoto.tif')
            query = {'flight_id': flight_id}
            update = {"$set": {
                "orthophoto_path": orthophoto_path,
                "orthophoto_source_crs": source_crs,
                "status": status
            }}
            client, db_collection = connectDb()
            db_collection.update_one(query, update, upsert=True)
        else:
            query = {'flight_id': flight_id}
            update = {"$set": {
                "status": status
            }}
            client, db_collection = connectDb()
            db_collection.update_one(query, update, upsert=True)
    except Exception as e:
        print('except', e)


def countFiles(path):
    file_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.lower().endswith(('.jpg', '.jpeg', '.tif', '.tiff')):
                file_count += 1
    return file_count


def lsfSubmitJob(lsfscript, flight_dir):
    try:
        result = subprocess.run([f'bsub < {lsfscript}'], shell=True,
                                capture_output=True, text=True, cwd=flight_dir)
        job_id = result.stdout.split('>')[0].split('<')[1]
        # logging.info({
        #     'service': 'lsf job submit',
        #     'message': f'submitted job {job_id}'
        # })
        return int(job_id)
    except Exception as e:
        logging.error({
            'service': 'lsf submit job',
            'message': e
        })
        return None


# TODO: what is the use of if/else when printing job status
def lsfMonitorJob(job_id, flight_id):
    if job_id:
        statusList = ["RUN", "PEND"]
        status = "RUN"
        logging.info({
            'service': 'lsf job monitoring',
            'message': f'{flight_id} - monitoring {job_id}'
        })
        while status in statusList:
            result = subprocess.run([f"bjobs -r {job_id}"], shell=True,
                                    capture_output=True, text=True)
            if len(result.stdout.split()) > 10:
                status = result.stdout.split()[10]
                if status == "RUN":
                    # print("Job %d is  running"%jobID)
                    pass
                elif status == "PEND":
                    print(f"Job {job_id} is pending. Status {status}\n")
                else:
                    pass
        result = subprocess.run([f"bjobs -r {job_id}"], shell=True,
                                capture_output=True, text=True)
        if len(result.stdout.split()) < 10:
            print(f"Job {job_id} is no longer running, Status: {status}")
        else:
            print(f"Job {job_id} is no longer running, Status: {status}")
        logging.info({
            'service': 'lsf job monitoring',
            'message': f'{flight_id} - {job_id} completed with status {status}'
        })
        return status
    return None
# if __name__ == '__main__':
#     flight_dir = sys.argv[1]
#     flight_id = sys.argv[2]
#     status = sys.argv[3]
#     update_ortho(flight_dir, flight_id, status)
