import uuid
import os
import subprocess
import pandas as pd
import numpy as np
from tqdm import tqdm
import utils
from config import config
import sys

sys.path.insert(0, '/home/jbshah/drone-pilot-upload/ortho_processing')
import ortho_intelligence


def acceptUpload(files, ortho_file):
    # files = []
    file_count = len(files)
    flight_id = str(uuid.uuid4())
    print(f'{flight_id} :: {ortho_file}')
    if any('.tif' in file.name.lower() for file in files):
        check_radiance_panels = True
    elif any('.jpg' in file.name.lower() for file in files):
        check_radiance_panels = False
    else:
        status_code, response = 400, {'status': 'failed',
                                      'reason': 'images not present'}
        # update csv with status and response and exit
        exit()

    flight_details = utils.createFolderStructure(flight_id, files,
                                                 check_radiance_panels)

    # explicit closing of files to empty filedescriptor (file pointers)
    for file in files:
        file.close()

    flight_details = utils.getExifInfo(flight_details)

    # adding metadata received from the user to the database
    flight_details['pilot_name'] = 'Rob Austin'
    flight_details['cloudiness'] = 'No data'
    flight_details['comments'] = ''
    flight_details[
        'display_name'] = f"{flight_details['mission_start_time']}" \
                          f"-{flight_details['cloudiness']}-" \
                          f"{flight_details['pilot_name']}"
    # these can be recomputed from flight_id, hence freeing up
    # database storage space
    del flight_details['flight_images']
    del flight_details['radiance_panels']
    del flight_details['misc_files']
    flight_details['num_files'] = file_count

    utils.insertDb(flight_details)

    status_code, response = 200, {'status': 'success'}
    # update csv with status code and response
    return flight_id
    # return flask.Response(response=json.dumps(response),
    #                               status=status_code)


def addOrtho(flight_id, flight_folder, ortho_file):
    ortho_folder = os.path.join(flight_folder, 'odm_orthophoto')
    if not os.path.exists(ortho_folder):
        os.makedirs(ortho_folder)
    original_ortho_cog = os.path.splitext(ortho_file)[0] + '_cog' + \
                         os.path.splitext(ortho_file)[1]
    os.rename(ortho_file, os.path.join(ortho_folder, 'odm_orthophoto.tif'))
    cog_file = os.path.join(ortho_folder, 'odm_orthophoto_cog.tif')
    if not os.path.exists(original_ortho_cog):
        subprocess.run(['rio', 'cogeo', 'create', original_ortho_cog, cog_file])
    else:
        os.rename(original_ortho_cog, cog_file)
    ortho_intelligence.generateVegIndices(cog_file, flight_folder)


def main():
    # excel_file = '/Users/jbshah/2023OrthoMapping.xlsx'
    excel_file = '/home/jbshah/2023OrthoMapping.xlsx'
    df = pd.read_excel(excel_file, header=0)
    # df = df.groupby('ortho')
    # print(df.first())
    df = df.groupby('ortho', as_index=False).agg(list)
    with open('/home/jbshah/oldDataMapping.json', 'w') as file:
        for index, row in tqdm(df.iterrows()):
            files = []
            for folder in row['raw_folder']:
                updated_folder = folder.replace(
                    '/rs1/shares/cals-research-station', '')
                files.extend([open(os.path.join(updated_folder, x), 'rb') for x
                              in os.listdir(updated_folder)])
            flight_id = acceptUpload(files, row['ortho'])
            flight_folder = os.path.join(config['flight_data_folder'],
                                         flight_id)
            ortho_file = row['ortho'].replace(
                '/rs1/shares/cals-research-station', '')
            file.write(f'{{ flight_id: {flight_id}, raw: {row["raw_folder"]}, '
                       f' old_ortho: {row["ortho"]} }}')
            break

    # for index, row in df.iterrows():
    #     if not (pd.isnull(row['raw_folder']) or pd.isnull(row['ortho'])):
    #         print(row['raw_folder'], row['ortho'])


utils.setup_logging()
main()
