import os
import uuid
import exiftool
import pymongo
# import psycopg2
# from PIL import Image
# from PIL.ExifTags import TAGS
from datetime import datetime
from pyzxing import BarCodeReader
from config import config
import pandas as pd
import geopandas



# TODO: Standardize datetime (maybe set all to UTC)

def findRadiancePanels(files, numBands, panelFolder, panelList):
    # TODO
    # get first few in one band
    # get last few in one band
    counter = 0
    possible_panels = []
    # print(files)
    for file in files:
        if counter >= 5:
            break
        if '_1.tif' in file:
            possible_panels.append(file)
            counter += 1

    counter = 0
    for file in reversed(files):
        if counter >= 5:
            break
        if '_1.tif' in file:
            possible_panels.append(file)
            counter += 1

    panels = []
    reader = BarCodeReader()
    for file in possible_panels:
        results = reader.decode(file)
        if 'format' in results[0].keys():
            panels.append(file)
    cleanedFileList = files
    for panel in panels:
        newUniqueFileName = str(uuid.uuid4())
        panelFileName = '_'.join(panel.split('_')[:-1])
        for i in range(1, numBands + 1):
            fileName = panelFileName + f'_{i}.tif'
            newFilePath = os.path.join(panelFolder,
                                       newUniqueFileName + f'_{i}.tif')
            os.rename(fileName, newFilePath)
            cleanedFileList.remove(fileName)
            panelList.append(newFilePath)

    return cleanedFileList, panelList


def calcBands(files):
    files = [file for file in files if '.tif' in file]
    current_file = '_'.join(os.path.split(files[0])[1].split('_')[:2])
    numBands = 1
    for file in files[1:]:
        if '_'.join(os.path.split(file)[1].split('_')[:2]) == current_file:
            numBands += 1
        else:
            break
    return numBands


def createFolderStructure(flight_type, files, location='./flights/'):
    flight_id = str(uuid.uuid4())
    if not os.path.exists(os.path.join(location, flight_id)):
        os.makedirs(os.path.join(location, flight_id))

    image_folder = os.path.join(location, flight_id, 'images')
    other_folder = os.path.join(location, flight_id, 'other_files')
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
    if not os.path.exists(other_folder):
        os.makedirs(other_folder)

    image_list = []
    panel_list = []
    other_list = []
    # TODO
    if flight_type == 'multispectral':
        # add files to tmp storage and then use them ahead
        temp_folder = os.path.join(location, flight_id, 'temp_storage')
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
        temp_files = []
        for file in files:
            if '.ds_store' not in file.filename.lower():
                filepath = os.path.join(temp_folder, os.path.split(
                    file.filename)[1].lower())
                file.save(filepath)
                temp_files.append(filepath)
        temp_files.sort()

        numBands = calcBands(temp_files)
        panel_folder = os.path.join(location, flight_id, 'panels')
        if not os.path.exists(panel_folder):
            os.makedirs(panel_folder)

        temp_files, panel_list = findRadiancePanels(temp_files, numBands,
                                                    panel_folder, panel_list)
        mapping_dict = {}
        for file in temp_files:
            name, file_ext = os.path.splitext(file)
            # TODO: check if these filenames provide information that needs
            #  to be preseved
            # TODO: fix .ds_store errors originating from mac file system
            if file_ext.lower() != '.tif':
                filepath = os.path.join(other_folder,
                                        str(uuid.uuid4()) + file_ext.lower())
                os.rename(file, filepath)
                other_list.append(filepath)
            else:
                fileName = '_'.join(file.split('_')[:-1])
                if fileName not in mapping_dict.keys():
                    mapping_dict[fileName] = str(uuid.uuid4())
                bandNumber = file.split('_')[-1]
                newFilePath = os.path.join(image_folder,
                                           mapping_dict[fileName] +
                                           f'_{bandNumber}')
                os.rename(file, newFilePath)
                image_list.append(newFilePath)

        # os.remove(temp_folder)
        os.rmdir(temp_folder)

    elif flight_type == 'rgb':
        for file in files:
            if '.ds_store' not in file.filename.lower():
                name, file_ext = os.path.splitext(file.filename)
                # TODO: check if these filenames provide information that needs
                #  to be preseved
                if file_ext.lower() != '.jpg':
                    filepath = os.path.join(other_folder,
                                            str(uuid.uuid4()) + file_ext.lower())
                    file.save(filepath)
                    other_list.append(filepath)
                else:
                    filepath = os.path.join(image_folder,
                                            str(uuid.uuid4()) + file_ext.lower())
                    file.save(filepath)
                    image_list.append(filepath)

    file_details = {
        'flight_id': flight_id,
        'images': image_list,
        'panels': panel_list,
        'other_files': other_list,
        'flight_type': flight_type,
        'upload_time': datetime.now()
    }
    return file_details


def calcGSD(exif_info,flight_type):
    sensor_width = config['sensor_information'][exif_info['EXIF:Model']][
        'sensor_width']
    altitude = exif_info['EXIF:GPSAltitude']
    if flight_type == 'mutispectral':
        image_width = exif_info['EXIF:ImageWidth']
    elif flight_type == 'rgb':
        image_width = exif_info['EXIF:ExifImageWidth']
    focal_length = exif_info['EXIF:FocalLength']
    return (altitude * sensor_width * 100) / (image_width * focal_length)



def getExifInfo(file_details):
    # TODO: exifinfo for multispec
    # TODO: get gps info added (and bounding box for the whole flight)

    et = exiftool.ExifTool()
    # print(et)
    # print(file_details['images'][0])
    with exiftool.ExifTool() as et:
        first_image_exif_info = et.get_metadata(file_details['images'][0])
    camera_make = first_image_exif_info['EXIF:Make']
    camera_model = first_image_exif_info['EXIF:Model']
    file_details['camera_make'] = camera_make
    file_details['camera_model'] = camera_model
    file_details['gsd'] = calcGSD(first_image_exif_info, file_details[
        'flight_type'])
    file_details['file_type'] = first_image_exif_info['File:FileType']
    # max_date, min_date = datetime.now()
    date_format = '%Y:%m:%d %H:%M:%S'
    # datetime.strptime(date_string, format_string)
    min_date = max_date = datetime.strptime(
        first_image_exif_info['EXIF:CreateDate'], date_format)

    coordinate_data = []
    with exiftool.ExifTool() as et:
        for image in file_details['images']:
            exif_info = et.get_metadata(image)
            image_date = datetime.strptime(exif_info['EXIF:CreateDate'],
                                           date_format)
            if image_date < min_date:
                min_date = image_date
            if image_date > max_date:
                max_date = image_date

            coordinate_data.append({
                'lat': exif_info['EXIF:GPSLatitude'],
                'long': exif_info['EXIF:GPSLongitude']
            })
    file_details['mission_start_time'] = min_date
    file_details['mission_end_time'] = max_date

    tempDF = pd.DataFrame(coordinate_data)
    geoDF = geopandas.GeoDataFrame(
        tempDF, geometry=geopandas.points_from_xy(tempDF.long, tempDF.lat),
        crs="EPSG:4326"
    )
    file_details['flight_bounding_box'] = geoDF.total_bounds
    if file_details['flight_type'] == 'rgb':
        print('rgb')
    elif file_details['flight_type'] == 'multispectral':
        print('multispec')
    return file_details

def insertDb(file_details):
    client = pymongo.MongoClient('localhost', username='admin',
                                 # password=getpass('Password: '),
                                 password='yolo',
                                 authMechanism='SCRAM-SHA-256')
    collection = client['drone-pilot']['flight-information']
    collection.insert_one(file_details)
# def saveFiles(files, metadata, location='./images/'):
#     experiment_id = str(uuid.uuid4())
#     # conscious choice of keeping the connection open till all files are
#     # saved and logged in db
#     conn, cursor = connectDb()
#     if not os.path.exists(os.path.join(location, experiment_id)):
#         os.makedirs(os.path.join(location, experiment_id))
#     for file in files:
#         name, file_ext = os.path.splitext(file.filename)
#         filepath = os.path.join(location,
#                                 experiment_id,
#                                 str(uuid.uuid4()) + file_ext)
#         file.save(filepath)
#         insertDb(conn, cursor, filepath, experiment_id, metadata)
#     conn.close()


# def connectDb():
#     connection = psycopg2.connect(database="drone_pilot",
#                                   host="localhost",
#                                   user="admin",
#                                   password="password",
#                                   port="5432")
#     return connection, connection.cursor()


# def insertDb(conn, cursor, file_location, experiment_id, metadata):
#     # conn, cursor = connectDb()
#     try:
#         cursor.execute(
#             f"""insert into file_information(experiment_id,file_location, metadata)
#             values('{experiment_id}','{file_location}', '{metadata}');""")
#         conn.commit()
#     except Exception as e:
#         print(e)

# def insertDb(conn, cursor, file_details, metadata):
#     print(file_details)
#     print("*********")
#     print(metadata)
#     # for file_location in file_details['images']:
#     #     try:
#     #         cursor.execute(
#     #             f"""insert into file_information(experiment_id,file_location, metadata)
#     #             values('{file_details["flight_id"]}','{file_location}',
#     #             '{metadata}');""")
#     #         conn.commit()
#     #     except Exception as e:
#     #         print(e)
#     # for file_location in file_details['panels']:
#     #     try:
#     #         cursor.execute(
#     #             f"""insert into file_information(experiment_id,file_location, metadata)
#     #             values('{file_details["flight_id"]}','{file_location}',
#     #             '{metadata}');""")
#     #         conn.commit()
#     #     except Exception as e:
#     #         print(e)
#     # for file_location in file_details['other_files']:
#     #     try:
#     #         cursor.execute(
#     #             f"""insert into file_information(experiment_id,file_location, metadata)
#     #             values('{file_details["flight_id"]}','{file_location}',
#     #             '{metadata}');""")
#     #         conn.commit()
#     #     except Exception as e:
#     #         print(e)
