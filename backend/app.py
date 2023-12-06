import json
import uuid

import flask
import logging
import sys
from flask import Flask
from flask_cors import CORS

import utils

app = Flask(__name__)
CORS(app)
logger = logging.getLogger('data_upload_api')
logger.setLevel(logging.INFO)


@app.route('/ping', methods=['GET'])
def ping():  # put application's code here
    response_body = {
        'status': 'healthy'
    }
    return flask.Response(response=json.dumps(response_body), status=200,
                          mimetype='application/json')


def file_sorter(x):
    return x.filename


# ping is not required for this API since it lives locally on individual
# workstations


@app.route('/imgproc', methods=['POST'])
def acceptUpload():
    try:
        if flask.request.method == 'POST':
            metadata = json.loads(flask.request.form['metadata'])
            files = flask.request.files.getlist("files")
            files = sorted(files, key=file_sorter)
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
            flight_details = utils.getExifInfo(flight_id, flight_details)

            # adding metadata received from the user to the database
            flight_details['pilot_name'] = metadata['pilotName']
            flight_details['cloudiness'] = metadata['cloudiness']
            flight_details['comments'] = metadata['comments']
            logging.info({
                'flight_id': flight_id,
                'service': 'database upload',
                'message': 'processing started'
            })
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
    app.run()
