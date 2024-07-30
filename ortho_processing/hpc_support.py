import utils

def get_file_count(flight_id):
    # gets all flights uploaded yesterday
    client, db_collection = utils.connectDb()
    query = {'flight_id': flight_id}
    result = db_collection.find(query)[0]
    return result['num_files']

def update_status(flight_id, status):
    client, db_collection = utils.connectDb()

if __name__ == '__main__':
    main()
