import json
import uuid
import flask
import logging
from flask import Flask, Request
from flask_cors import CORS
import utils
from config import config
# import sentry_sdk


class CustomRequest(Request):
    def __init__(self, *args, **kwargs):
        super(CustomRequest, self).__init__(*args, **kwargs)
        self.max_form_parts = config['max_file_count']


# sentry_sdk.init(
#     dsn="http://b309d193beabb2ee01d0b04013ee8554@20.169.137.216//3",
#     # Set traces_sample_rate to 1.0 to capture 100%
#     # of transactions for performance monitoring.
#     traces_sample_rate=1.0,debug=True,environment='test'
# )

app = Flask(__name__)
app.request_class = CustomRequest
CORS(app)


# app.config['MAX_CONTENT_LENGTH'] = 150 * 1024 * 1024 * 1024

# ping is not required for this API since it lives locally on individual
# workstations
@app.route('/ping', methods=['GET'])
def ping():
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
            files = sorted([file for file in flask.request.files.getlist("files") if not file.filename.lower().startswith('.')],
                           key=file_sorter)
            file_count = len(files)
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

            flight_details = utils.createFolderStructure(flight_id, files,
                                                         check_radiance_panels)

            # explicit closing of files to empty filedescriptor (file pointers)
            for file in files:
                file.close()

            flight_details = utils.getExifInfo(flight_details)

            # adding metadata received from the user to the database
            flight_details['pilot_name'] = metadata['pilotName']
            flight_details['cloudiness'] = metadata['cloudiness']
            flight_details['comments'] = metadata['comments']
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
            flight_details['num_files'] = file_count

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
