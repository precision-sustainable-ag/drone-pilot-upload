config = {
    # 'database_details': {
    #     'host': 'localhost',
    #     'username': 'admin',
    #     'password': 'yolo',
    #     'database': 'drone-pilot',
    #     'auth_source': 'admin',
    #     'collection': 'flight-information'
    # },
    # 'flights_dir': '/rs1/shares/cals-research-station/sandhills/transfer'
    #                '/flights/',
    'mount_dir': '/rs1/shares/cals-research-station/',
    'code_dir': '/usr/local/usrapps/drones/drone-pilot-upload/',
    'log_file': '/home/hpc.drone.svc/ondemand/data/drone-pilot-upload/cron_log.json',
    'python_exec': '/usr/local/usrapps/drones/drone-pilot-upload/backend/venv/bin/python3',
    'scratch_dir': '/share/drones/hpc.drone.svc/tmp',
    'database_details': {
        'host': 'drone-pilot-test.bsgdbxt.mongodb.net',
        'username': 'mspinega',
        'password': 'KmLFKqC3V1fGLCDw',
        'database': 'flight-information',
        'auth_source': 'flight-information',
        'collection': 'flight-information',
        'auth_mechanism': 'SCRAM-SHA-1',
        'connection_string': 'mongodb+srv://admin:Children1921@drone-pilot-project.svxbuw.mongodb.net/?retryWrites=true&w=majority&appName=drone-pilot-project'
        # 'connection_string' : 'mongodb+srv://mspinega:KmLFKqC3V1fGLCDw@drone-pilot-test.bsgdbxt.mongodb.net/?retryWrites=true&w=majority&appName=drone-pilot-test'
    },
}
