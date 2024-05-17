import os
import subprocess
import multiprocessing
import concurrent.futures
from datetime import datetime, timedelta
import utils
from config import config

# gets all flights uploaded yesterday
client, db_collection = utils.connectDb()
yesterday = (datetime.now() - timedelta(days=1)).date()
today = datetime.now().date()
# adding midnight as hour,min,sec (full datetime object is needed for mongo)
yesterday = datetime.combine(yesterday, datetime.min.time())
today = datetime.combine(today, datetime.min.time())
query = {"upload_time": {"$gte": yesterday, "$lt": today}}

results = db_collection.find(query)

records_to_process = []
for row in results:
    if 'status' not in row.keys():
        records_to_process.append(row['flight_id'])
    elif row['status'] not in ['processed', 'processing']:
        records_to_process.append(row['flight_id'])


# send these records for processing
# add multiprocessing/multithreading when triggering
def trigger(flight_id):
    flight_dir = os.path.join(config['data_dir'], flight_id)
    results = subprocess.run(['./generate_ortho.sh', flight_dir, flight_id])


num_workers = multiprocessing.cpu_count()
with concurrent.futures.ThreadPoolExecutor(
        max_workers=num_workers) as executor:
    executor.map(trigger, records_to_process)
