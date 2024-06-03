config = {
    # 'flight_data_folder': '/data/transfer/',
    'flight_data_folder': '/Users/jbshah/_p/test/backend_storage/flights/',
    #  TODO: review usage of this field
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
        'auth_source': 'admin',
        'collection': 'flight-information'
    },
    'log_file': './logs/log_',
    'max_file_count': 13000
}
