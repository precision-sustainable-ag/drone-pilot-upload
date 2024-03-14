import os
# import sys
import json
import uuid
import exiftool
import pymongo
import pandas as pd
import shapely
from shapely.geometry import box, mapping
import geopandas
import logging
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
from pyzxing import BarCodeReader
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


# setup_logging()

def changeCRS(source_crs, target_crs, source_polygon):
    transformer = pyproj.Transformer.from_crs(source_crs, target_crs,
                                              always_xy=True)
    target_polygon = []
    for coordinate in source_polygon:
        x, y = transformer.transform(coordinate[0], coordinate[1])
        target_polygon.append([x, y])
    return target_polygon
# TODO: Standardize datetime (maybe set all to UTC)


def findRadiancePanels(flight_id, files, num_bands, panel_folder):
    """
    As per pre-determined flow, the radiance panels would present either at the
    start of the flight or at the end. Hence, this function iterates over the
    first five and last five primary band images to look for radiance panels
    :param flight_id: unique identifier for the flight
    :param files: list of image files
    :param num_bands: number of bands - numBands function
    :param panel_folder: location to store radiance panel images
    :return: list of images and list of radiance panel images
    """
    counter = 0
    possible_panels = []
    logging.info({
        'flight_id': flight_id,
        'service': 'radiance panels',
        'message': 'processing started'
    })
    for file in files:
        if counter >= 5:
            break
        # the first band is considered as the primary band
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

    primary_band_panels = []
    # use qrcode/barcode reader to identify radiance panels
    reader = BarCodeReader()
    for file in possible_panels:
        results = reader.decode(file)
        if 'format' in results[0].keys():
            primary_band_panels.append(file)
    logging.info({
        'flight_id': flight_id,
        'service': 'radiance panels',
        'message': 'primary band radiance panels found'
    })
    # move radiance panel images in all bands to panel folder and remove them
    # from the list of images to use for orthomosaic generation
    panel_images = []
    flight_image_list = files
    for panel in primary_band_panels:
        new_file_name = str(uuid.uuid4())
        original_no_band_filename = '_'.join(panel.split('_')[:-1])
        for i in range(1, num_bands + 1):
            source_file_name = original_no_band_filename + f'_{i}.tif'
            destination_file_path = os.path.join(panel_folder,
                                                 new_file_name + f'_{i}.tif')
            os.rename(source_file_name, destination_file_path)
            flight_image_list.remove(source_file_name)
            panel_images.append(destination_file_path)

    logging.info({
        'flight_id': flight_id,
        'service': 'radiance panels',
        'message': 'list of panels and images computed'
    })
    return flight_image_list, panel_images


def calcBands(flight_id, files):
    """
    iterates over the sorted list of files until the band number changes,
    and then return the number of bands
    :param flight_id: unique identifier for the flight
    :param files: sorted list of image files
    :return: number of bands
    """
    logging.info({
        'flight_id': flight_id,
        'service': 'num bands',
        'message': 'processing started'
    })
    files = [file for file in files if '.tif' in file]
    current_file = '_'.join(os.path.split(files[0])[1].split('_')[:2])
    num_bands = 1
    for file in files[1:]:
        if '_'.join(os.path.split(file)[1].split('_')[:2]) == current_file:
            num_bands += 1
        else:
            break
    logging.info({
        'flight_id': flight_id,
        'service': 'num_bands',
        'message': 'processing complete'
    })
    return num_bands


def createFolderStructure(flight_id, files, check_radiance_panels=False):
    """
    creates the folder structure for flight data storage
    :param flight_id: unique identifier for the flight
    :param files: array of files in the folder uploaded
    :param check_radiance_panels: boolean to determine if radiance panels
    need to found
    :return: flight_id, flight_images, radiance_panels, misc_files, num_bands,
    upload_time in one json object
    """
    # create a new flight identifier
    logging.info({
        'flight_id': flight_id,
        'service': 'create folder structure',
        'message': 'processing started'
    })
    parent_folder = os.path.join(config['flight_data_folder'], flight_id)
    # create the required folders for storing the images and misc files
    if not os.path.exists(parent_folder):
        os.makedirs(parent_folder)
    image_folder = os.path.join(parent_folder, 'images')
    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
    other_folder = os.path.join(parent_folder, 'other_files')
    if not os.path.exists(other_folder):
        os.makedirs(other_folder)

    image_list, misc_files = [], []

    if check_radiance_panels:
        # add files to tmp storage and then use them
        temp_folder = os.path.join(parent_folder, 'temp_storage')
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
        temp_files = []
        for file in files:
            # ignore the files created by macos - required only for dev
            if '.ds_store' not in file.filename.lower():
                filepath = os.path.join(temp_folder, os.path.split(
                    file.filename)[1].lower())
                file.save(filepath)
                temp_files.append(filepath)
        temp_files.sort()

        panel_folder = os.path.join(parent_folder, 'panels')
        if not os.path.exists(panel_folder):
            os.makedirs(panel_folder)

        num_bands = calcBands(flight_id, temp_files)

        temp_files, panel_list = findRadiancePanels(flight_id, temp_files,
                                                    num_bands, panel_folder)

        logging.info({
            'flight_id': flight_id,
            'service': 'create folder structure',
            'message': 'separating flight images and misc files'
        })
        # maintain a mapping of original file names and unique file names (
        # since all bands need to have the same prefix)
        mapping_dict = {}
        for file in temp_files:
            name, file_ext = os.path.splitext(file)
            # TODO: fix .ds_store errors originating from mac file system -
            #  line 153 should take care of it
            if file_ext.lower() != '.tif':
                filepath = os.path.join(other_folder,
                                        str(uuid.uuid4()) + file_ext.lower())
                os.rename(file, filepath)
                misc_files.append(filepath)
            else:
                file_name = '_'.join(file.split('_')[:-1])
                if file_name not in mapping_dict.keys():
                    mapping_dict[file_name] = str(uuid.uuid4())
                band_number = file.split('_')[-1]
                new_file_path = os.path.join(image_folder,
                                             f'{mapping_dict[file_name]}_'
                                             f'{band_number}')
                os.rename(file, new_file_path)
                image_list.append(new_file_path)

        os.rmdir(temp_folder)

    else:
        panel_list = []
        # working on the assumption that if radiance panels are checked,
        # images are multispectral else RGB
        num_bands = 0
        logging.info({
            'flight_id': flight_id,
            'service': 'create folder structure',
            'message': 'separating flight images and misc files'
        })
        for file in files:
            if '.ds_store' not in file.filename.lower():
                name, file_ext = os.path.splitext(file.filename)
                if file_ext.lower() != '.jpg':
                    filepath = os.path.join(other_folder,
                                            f'{str(uuid.uuid4())}{file_ext.lower()}')
                    file.save(filepath)
                    misc_files.append(filepath)
                else:
                    filepath = os.path.join(image_folder,
                                            f'{str(uuid.uuid4())}{file_ext.lower()}')
                    file.save(filepath)
                    image_list.append(filepath)
    logging.info({
        'flight_id': flight_id,
        'service': 'create folder structure',
        'message': 'processing complete'
    })
    return {
        'flight_id': flight_id,
        'flight_images': image_list,
        'radiance_panels': panel_list,
        'misc_files': misc_files,
        'num_bands': num_bands,
        'upload_time': datetime.now()
        # 'flight_type': flight_type,
    }


def calcGSD(exif_info):
    """
    computes ground sampling distance that is used to generate orthomosaic
    with the best resolution
    :param exif_info: common exif information - from one image of the flight
    :return: ground sampling distance
    """
    if exif_info['EXIF:Model'] in config['sensor_information'].keys():
        sensor_information = config['sensor_information'][
            exif_info['EXIF:Model']]
        sensor_width = sensor_information['sensor_width']
        altitude = exif_info['EXIF:GPSAltitude']
        image_width = exif_info[sensor_information['image_width_exif_tag']]
        # if flight_type == 'mutispectral':
        #     image_width = exif_info['EXIF:ImageWidth']
        # elif flight_type == 'rgb':
        #     image_width = exif_info['EXIF:ExifImageWidth']
        focal_length = exif_info['EXIF:FocalLength']
        return (altitude * sensor_width * 100) / (image_width * focal_length)
    return 0.001


def getExifInfo(flight_details):
    # TODO: exifinfo for multispec
    # TODO: get gps info added (and bounding box for the whole flight)

    logging.info({
        'flight_id': flight_details['flight_id'],
        'service': 'exif information',
        'message': 'processing started'
    })
    with exiftool.ExifTool() as et:
        first_image_exif_info = et.get_metadata(
            flight_details['flight_images'][0])
    camera_make = first_image_exif_info['EXIF:Make']
    camera_model = first_image_exif_info['EXIF:Model']
    flight_details['camera_make'] = camera_make
    flight_details['camera_model'] = camera_model
    flight_details['gsd'] = calcGSD(first_image_exif_info)
    flight_details['file_type'] = first_image_exif_info['File:FileType']
    logging.info({
        'flight_id': flight_details['flight_id'],
        'service': 'exif information',
        'message': 'extracted common exif information'
    })
    date_format = '%Y:%m:%d %H:%M:%S'
    min_date = max_date = datetime.strptime(
        first_image_exif_info['EXIF:CreateDate'], date_format)

    coordinate_data = []
    with exiftool.ExifTool() as et:
        for image in flight_details['flight_images']:
            exif_info = et.get_metadata(image)
            image_date = datetime.strptime(exif_info['EXIF:CreateDate'],
                                           date_format)
            if image_date < min_date:
                min_date = image_date
            if image_date > max_date:
                max_date = image_date
            # TODO: coordinates also have s/w (which makes it negative)
            coordinate_data.append({
                'Latitude': exif_info['EXIF:GPSLatitude'] if exif_info[
                                                                 'EXIF:GPSLatitudeRef'].lower() == 'n' else -(
                exif_info['EXIF:GPSLatitude']),
                'Longitude': exif_info['EXIF:GPSLongitude'] if exif_info[
                                                                   'EXIF:GPSLongitudeRef'].lower() == 'e' else -(
                exif_info['EXIF:GPSLongitude']),
            })
    flight_details['mission_start_time'] = min_date
    flight_details['mission_end_time'] = max_date
    logging.info({
        'flight_id': flight_details['flight_id'],
        'service': 'exif information',
        'message': 'extracted flight time and gps information'
    })
    # TODO: Check if geoDF can be added to the database or atleast geometry
    #  objects
    # TODO: Add -ve latitude and longitude (for west/south)
    temp_df = pd.DataFrame(coordinate_data)
    geo_df = geopandas.GeoDataFrame(
        temp_df, geometry=geopandas.points_from_xy(temp_df.Longitude,
                                                   temp_df.Latitude),
        crs="EPSG:4326"
    )
    # flight_details['flight_polygon'] = json.loads(shapely.to_geojson(
    #     geometry.Polygon(geo_df['geometry'].tolist())))
    flight_details['flight_polygon'] = {"type": "GeometryCollection",
                                        "geometries": [json.loads(x) for x in
                                                       shapely.to_geojson(
                                                           geo_df[
                                                               'geometry'].tolist())]}
    total_bounds = geo_df.total_bounds
    xmin, ymin, xmax, ymax = total_bounds.tolist()
    geom = box(xmin, ymin, xmax, ymax)
    original_polygon = [list(x) for x in mapping(
        geom)['coordinates'][0]][:4]
    new_polygon = changeCRS('EPSG:4326', 'EPSG:3857', original_polygon)
    flight_details['flight_bounding_box'] = original_polygon
    flight_details['flight_bounding_box_3857'] = new_polygon
    logging.info({
        'flight_id': flight_details['flight_id'],
        'service': 'exif information',
        'message': 'computed flight bounds'
    })
    return flight_details


def insertDb(file_details):
    database_details = config['database_details']
    client = pymongo.MongoClient(database_details['host'],
                                 username=database_details['username'],
                                 password=database_details['password'],
                                 authMechanism='SCRAM-SHA-256')
    collection = client[database_details['database']][database_details[
        'collection']]
    collection.insert_one(file_details)
