# TODO: need to change M3M sensor width and need to add zenmuse p1 sensor width
config = {
    # 'flight_data_folder': '/data/transfer/',
    'flight_data_folder': '/Users/jbshah/_p/drone-pilot-upload/backend/flights',
    'sensor_information': {
        'Altum-PT': {
            # this is for the multispec sensor
            'sensor_width': 7.12,
            'image_width_exif_tag': 'EXIF:ImageWidth'
        },
        'M3M': {
            'sensor_width': 35,
            'image_width_exif_tag': 'EXIF:ExifImageWidth'
        }
    },
    'database_details': {
        'host': 'localhost',
        'username': 'admin',
        'password': 'yolo',
        'database': 'drone-pilot',
        'collection': 'flight-information'
    },
    'log_file': './logs/log_'
}
