# services/db.py

import pymongo
from config import config


def connect_db() -> tuple[pymongo.MongoClient, pymongo.collection.Collection]:
    d = config["database_details"]
    client = pymongo.MongoClient(d["connection_string"])
    collection = client[d["database"]][d["collection"]]
    return client, collection
