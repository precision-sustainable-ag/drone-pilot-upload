import json
import uuid
import flask
import logging
from flask import Flask, Request
from flask_cors import CORS
from flask import send_from_directory
import os
import utils
from config import config


# import sentry_sdk


class CustomRequest(Request):
    def __init__(self, *args, **kwargs):
        super(CustomRequest, self).__init__(*args, **kwargs)
        self.max_form_parts = config['max_file_count']

LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, 'app.log'),
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# sentry_sdk.init(
#     dsn="http://b309d193beabb2ee01d0b04013ee8554@20.169.137.216//3",
#     # Set traces_sample_rate to 1.0 to capture 100%
#     # of transactions for performance monitoring.
#     traces_sample_rate=1.0,debug=True,environment='test'
# )

app = Flask(__name__)
app.request_class = CustomRequest
CORS(app)

# Path to the frontend build directory
FRONTEND_BUILD_DIR = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'build')

@app.route('/frontend/<path:path>')
def serve_frontend_static(path):
    return send_from_directory(FRONTEND_BUILD_DIR, path)

@app.route('/frontend')

@app.route('/frontend/<path:path>')
def serve_frontend_index(path=""):
    index_path = os.path.join(FRONTEND_BUILD_DIR, 'index.html')
    print(f"🧭 Trying to serve: {index_path} (exists={os.path.exists(index_path)})")
    return send_from_directory(FRONTEND_BUILD_DIR, 'index.html')

# Serve frontend static files (e.g., JS, CSS)
@app.route('/static/<path:path>')
def serve_static(path):
    return send_from_directory(os.path.join(FRONTEND_BUILD_DIR, 'static'), path)

# Serve index.html for any frontend route not matched above
@app.route('/', defaults={'path': ''})

@app.route('/<path:path>')
def serve_frontend(path):
    if path != "" and os.path.exists(os.path.join(FRONTEND_BUILD_DIR, path)):
        return send_from_directory(FRONTEND_BUILD_DIR, path)
    else:
        return send_from_directory(FRONTEND_BUILD_DIR, 'index.html')

# app.config['MAX_CONTENT_LENGTH'] = 150 * 1024 * 1024 * 1024

# ping is not required for this API since it lives locally on individual
# workstations
@app.route('/ping', methods=['GET'])
def ping():
    logging.info("✅ /ping endpoint was hit")
    response_body = {
        'status': 'healthy'
    }
    return flask.Response(response=json.dumps(response_body), status=200,
                          mimetype='application/json')


def file_sorter(x):
    return x.filename


@app.route('/imgproc', methods=['POST'])
def acceptUpload():
    try:
        if flask.request.method == 'POST':
            metadata = json.loads(flask.request.form['metadata'])
            research_station = config['research_station_mapping'][
                metadata['research_station']]
            files = sorted(
                [file for file in flask.request.files.getlist("files") if
                 not file.filename.lower().startswith('.')],
                key=file_sorter)
            img_count = len([file for file in files if
                              file.filename.lower().endswith(
                                  ('.jpg', '.jpeg', '.tif', '.tiff'))])
            flight_id = str(uuid.uuid4())
            logging.info({
                'flight_id': flight_id,
                'service': 'data upload',
                'message': 'images received'
            })

            # check the type of the images - used later (multispectral images
            # have some pictures of the calibration panels)
            # TODO: Change this to use the make and model of the camera to
            #  make decisions
            if any('.tif' in file.filename.lower() for file in files):
                check_radiance_panels = True
            elif any('.jpg' in file.filename.lower() for file in files):
                check_radiance_panels = False
            else:
                status_code, response = 400, {'status': 'failed',
                                              'reason': 'images not present'}
                logging.error({
                    'flight_id': flight_id,
                    'service': 'data upload',
                    'status_code': 400,
                    'message': 'supported images not present'
                })
                return flask.Response(response=json.dumps(response),
                                      status=status_code)

            flight_details = utils.createFolderStructure(flight_id,
                                                         research_station,
                                                         files,
                                                         check_radiance_panels)

            # explicit closing of files to empty filedescriptor (file pointers)
            for file in files:
                file.close()

            flight_details = utils.getExifInfo(flight_details)

            # adding metadata received from the user to the database
            flight_details['pilot_name'] = metadata['pilotName']
            flight_details['cloudiness'] = metadata['cloudiness']
            flight_details['comments'] = metadata['comments']
            flight_details['research_station'] = research_station
            flight_details[
                'display_name'] = f"{flight_details['mission_start_time']}" \
                                  f"-{flight_details['cloudiness']}-" \
                                  f"{flight_details['pilot_name']}"
            logging.info({
                'flight_id': flight_id,
                'service': 'database upload',
                'message': 'processing started'
            })

            # these can be recomputed from flight_id, hence freeing up
            # database storage space
            del flight_details['flight_images']
            del flight_details['radiance_panels']
            del flight_details['misc_files']

            # adding number of files for checking data upload status
            # TODO: update this to num_imgs instead
            flight_details['num_files'] = img_count

            utils.insertDb(flight_details)

            status_code, response = 200, {'status': 'success'}
            logging.info({
                'flight_id': flight_id,
                'service': 'data upload',
                'status_code': 200,
                'message': 'processing complete'
            })
            return flask.Response(response=json.dumps(response),
                                  status=status_code)
    except Exception as e:
        logging.error({
            'service': 'data upload',
            'status_code': 500,
            'message': e
        })
        status_code, response = 500, {'status': 'internal server error'}
        return flask.Response(response=json.dumps(response), status=status_code,
                              mimetype='application/json')


if __name__ == '__main__':
    utils.setup_logging()
    app.run()
