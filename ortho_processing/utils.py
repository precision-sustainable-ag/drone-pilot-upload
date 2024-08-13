'''
This script serves two functions:
1. Has helper code for cron.py
2. Has update_ortho code that is triggered if the script is called directly
instead of importing - this communicates with db and is the only part
responsible for inserts/updates into the database
'''

import os
import sys
import pyproj
import pymongo
from config import config


# TODO: confirm the conversion is correct and check if this info is enough
def readCRS(flight_dir):
    crs_file = os.path.join(flight_dir, 'odm_georeferencing', 'proj.txt')
    with open(crs_file, 'r') as file:
        crs_string = file.readline()
    return f'EPSG:{(pyproj.CRS.from_string(crs_string)).to_epsg()}'


def connectDb():
    database_details = config['database_details']
    client = pymongo.MongoClient(database_details['host'],
                                 username=database_details['username'],
                                 password=database_details['password'],
                                 authSource=database_details['auth_source'],
                                 authMechanism='SCRAM-SHA-1')
    collection = client[database_details['database']][database_details[
        'collection']]
    return client, collection


def update_ortho(flight_dir, flight_id, status):
    try:
        if status == 'processed':
            source_crs = readCRS(flight_dir)

            orthophoto_path = os.path.join(flight_id, 'odm_orthophoto',
                                           'odm_orthophoto.tif')
            cog_path = os.path.join(flight_id, 'odm_orthophoto',
                                    'odm_orthophoto_cog.tif')
            veg_index_folder = os.path.join(flight_id, 'veg_indices')

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
        # elif status == 'processing':
        #     query = {'flight_id': flight_id}
        #     update = {"$set": {
        #         "status": "processing"
        #     }}
        #     client, db_collection = connectDb()
        #     db_collection.update_one(query, update, upsert=True)
        else:
            query = {'flight_id': flight_id}
            update = {"$set": {
                "status": status
            }}
            client, db_collection = connectDb()
            db_collection.update_one(query, update, upsert=True)
    except Exception as e:
        print('except', e)


if __name__ == '__main__':
    flight_dir = sys.argv[1]
    flight_id = sys.argv[2]
    status = sys.argv[3]
    update_ortho(flight_dir, flight_id, status)
