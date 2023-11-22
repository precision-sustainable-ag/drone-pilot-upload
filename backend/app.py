import json
import flask
import logging
import sys
from flask import Flask
from flask_cors import CORS

import utils

app = Flask(__name__)
CORS(app)
logger = logging.getLogger()
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


@app.route('/imgproc', methods=['POST'])
def acceptUpload():
    # logging.info(flask.request)
    try:
        # print(flask.request.form)
        if flask.request.method == 'POST':
            formData = flask.request.form
            metadata = json.loads(formData['metadata'])
            files = flask.request.files.getlist("files")
            files = sorted(files, key=file_sorter)
            # files.sort()
            # determine flight type
            # TODO: check if there's a way to remove/reduce the loop complexity
            if any('.tif' in file.filename.lower() for file in files):
                flight_type = 'multispectral'
            elif any('.jpg' in file.filename.lower() for file in files):
                flight_type = 'rgb'
            else:
                status_code, response = 400, {'status': 'failed', 'reason':
                    'images not present'}
                return flask.Response(response=json.dumps(response),
                                      status=status_code)

            file_details = utils.createFolderStructure(flight_type, files)
            file_details = utils.getExifInfo(file_details)
            file_details['pilot_name'] = metadata['pilotName']
            file_details['cloudiness'] = metadata['cloudiness']
            file_details['comments'] = metadata['comments']
            # metadata['camera_make'] = file_details['camera_make']
            # metadata['camera_model'] = file_details['camera_model']
            # metadata['mission_start_time'] = file_details['mission_start_time']
            # metadata['mission_end_time'] = file_details['mission_end_time']
            # metadata['color_representation'] = file_details['flight_type']
            # metadata = json.dumps(metadata, default=str)
            # print(file_details)
            # print("********")
            # print("********")
            # print(metadata)
            # conn, cursor = utils.connectDb()
            # utils.insertDb(conn, cursor, file_details, metadata)
            utils.insertDb(file_details)

        status_code, response = 200, {'status': 'success'}
        return flask.Response(response=json.dumps(response), status=status_code)
    except Exception as e:
        print(e)
        status_code, response = 400, {'status': 'error, bad req'}
        return flask.Response(response=json.dumps(response), status=status_code,
                              mimetype='application/json')


if __name__ == '__main__':
    app.run()
