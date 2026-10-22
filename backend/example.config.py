import os

config = {
    'data_root': os.environ.get(
        'DPU_DATA_ROOT',
        '/tmp/drone-pilot-upload/data'
    ),
    'id_dir': os.environ.get(
        'DPU_ID_DIR',
        'site-id'
    ),
    'name_dir': os.environ.get(
        'DPU_NAME_DIR',
        'site-name'
    ),

    'flight_data_folder': os.environ.get(
        'DPU_FLIGHT_DATA_FOLDER',
        '/tmp/drone-pilot-upload/flights'
    ),

    'sensor_information': {
        'Altum-PT': {
            'sensor_width': 7.12,
            'image_width_exif_tag': 'EXIF:ImageWidth'
        },
        'M3M': {
            'sensor_width': 35,
            'image_width_exif_tag': 'EXIF:ExifImageWidth'
        }
    },

    'database_details': {
        'host': os.environ.get('DPU_MONGODB_HOST', 'localhost'),
        'username': os.environ.get('DPU_MONGODB_USERNAME', ''),
        'password': os.environ.get('DPU_MONGODB_PASSWORD', ''),
        'database': os.environ.get(
            'DPU_MONGODB_DATABASE',
            'flight-information'
        ),
        'auth_source': os.environ.get(
            'DPU_MONGODB_AUTH_SOURCE',
            'flight-information'
        ),
        'collection': os.environ.get(
            'DPU_MONGODB_COLLECTION',
            'flight-information'
        ),
        'connection_string': os.environ.get(
            'DPU_MONGODB_CONNECTION_STRING',
            ''
        )
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

    'log_file': os.environ.get(
        'DPU_LOG_FILE',
        '/tmp/drone-pilot-upload/app.log'
    ),

    'exif_tool_path': os.environ.get(
        'DPU_EXIF_TOOL_PATH',
        '/usr/bin/exiftool'
    ),

    'max_file_count': int(
        os.environ.get('DPU_MAX_FILE_COUNT', '13000')
    )
}
