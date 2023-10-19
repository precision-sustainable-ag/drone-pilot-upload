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


@app.route('/imgproc', methods=['POST'])
def acceptUpload():
    # logging.info(flask.request)
    try:
        # print(flask.request.form)
        if flask.request.method == 'POST':
            formData = flask.request.form
            metadata = formData['metadata']
            files = flask.request.files.getlist("files")
            utils.saveFiles(files, metadata)

        return flask.Response(response='success', status=200)
    except Exception as e:
        print(e)
        status_code, response = 400, {'status': 'error, bad req'}
        return flask.Response(response=json.dumps(response), status=status_code,
                              mimetype='application/json')


if __name__ == '__main__':
    app.run()
