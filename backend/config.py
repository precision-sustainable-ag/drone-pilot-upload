
config = {
    # 'flight_data_folder': '/data/transfer/',
    # 'flight_data_folder': '/Users/jbshah/_p/test/backend_storage/flights/',
    'flight_data_folder': '/Users/jbshah/_p/test/backend_storage_v2/',
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
    'research_station_mapping': {
        "Border Belt Tobacco Research Station": "border",
        "Central Crops Research Station": "central",
        "Horticultural Crops Research Station - Castle Hayne": "castle",
        "Horticultural Crops Research Station - Clinton": "clinton",
        "Lower Coastal Plain / Cunningham Research Station": "cunningham",
        "Mountain Research Station": "mountain",
        "Mountain Horticultural Crops Research and Extension Center": "mountainhort",
        "Oxford Tobacco Research Station": "oxford",
        "Peanut Belt Research Station": "peanut",
        "Piedmont Research Station": "piedmont",
        "Sandhills Research Station": "sandhills",
        "Tidewater Research Station": "tidewater",
        "Upper Coastal Plain Research Station": "uppercoastal",
        "Upper Mountain Research Station": "uppermountain",
        "Upper Piedmont Research Station": "upperpiedmont",
        "Caswell Research Station": "caswell",
        "Cherry Research Station": "cherry",
        "Umstead Research Station": "umstead",
        "Virtual Research Station": "virtual"
    },
    'log_file': './logs/log_',
    'max_file_count': 13000
}
