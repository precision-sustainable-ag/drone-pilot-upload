import os

config = {
    # 'flight_data_folder': '/rsstu/users/s/screberg/mixed_research_data/app_1_data/',
    # 'flight_data_folder': '/Users/jbshah/_p/test/backend_storage/flights/',
    # 'flight_data_folder': '/Users/jbshah/_p/test/backend_storage_v2/',
    'flight_data_folder': '/rs1/shares/cals-research-station',
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
        'host': 'drone-pilot-test.bsgdbxt.mongodb.net',
        'username': 'mspinega',
        'password': 'KmLFKqC3V1fGLCDw',
        'database': 'flight-information',
        'auth_source': 'flight-information',
        'collection': 'flight-information',
        'auth_mechanism': 'SCRAM-SHA-1',
        'connection_string': 'mongodb+srv://admin:REDACTED@drone-pilot-project.svxbuw.mongodb.net/?retryWrites=true&w=majority&appName=drone-pilot-project'
        # 'connection_string' : 'mongodb+srv://mspinega:REDACTED@drone-pilot-test.bsgdbxt.mongodb.net/?retryWrites=true&w=majority&appName=drone-pilot-test'
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
    # 'log_file': '/usr/local/usrapps/drones/drone-pilot-upload/logs/app.log',
    'log_file':  os.path.join(os.environ['HOME'], 'ondemand', 'data', 'drone-pilot-upload', 'app.log'),
    'exif_tool_path': '/usr/local/usrapps/drones/exiftool/Image-ExifTool-13.31/bin/exiftool',
    'max_file_count': 13000
}
