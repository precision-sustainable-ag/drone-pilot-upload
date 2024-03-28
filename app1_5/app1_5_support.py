import os
import sys
import pymongo
import pyproj

def connectDb():
    database_details = {
        'host': 'localhost',
        'username': 'admin',
        'password': 'yolo'
    }
    client = pymongo.MongoClient(database_details['host'],
                                 username=database_details['username'],
                                 password=database_details['password'],
                                 authMechanism='SCRAM-SHA-256')
    collection = client[database_details['database']][database_details[
        'collection']]
    return client, collection


# TODO: confirm the conversion is correct and check if this info is enough
def readCRS(flight_dir):
    crs_file = os.path.join(flight_dir, 'odm_georeferencing', 'proj.txt')
    with open(crs_file, 'r') as file:
        crs_string = file.readline()
    return f'EPSG:{(pyproj.CRS.from_string(crs_string)).to_epsg()}'


def main():
    flight_dir = sys.argv[1]
    flight_id = sys.argv[2]

    source_crs = readCRS(flight_dir)
    query = {'flight_id': flight_id}
    orthophoto_path = os.path.join(flight_dir, 'odm_orthophoto',
                                   'odm_orthophoto.tif')
    cog_path = os.path.join(flight_dir, 'odm_orthophoto',
                                   'cog.tif')
    veg_index_folder - os.path.join(flight_dir, 'veg_indices')

    update = {"$set": {
        "orthophoto_path": orthophoto_path,
        "cog_path": cog_path,
        "orthophoto_source_crs": source_crs,
        "veg_index_folder": veg_index_folder,
    }}

    client, db_collection = utils.connectDb()
    db_collection.update(query, update)
