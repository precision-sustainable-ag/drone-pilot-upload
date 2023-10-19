import os
import uuid
import psycopg2


def saveFiles(files, metadata, location='./images/'):
    experiment_id = str(uuid.uuid4())
    # conscious choice of keeping the connection open till all files are
    # saved and logged in db
    conn, cursor = connectDb()
    if not os.path.exists(os.path.join(location, experiment_id)):
        os.makedirs(os.path.join(location, experiment_id))
    for file in files:
        name, file_ext = os.path.splitext(file.filename)
        filepath = os.path.join(location,
                                experiment_id,
                                str(uuid.uuid4()) + file_ext)
        file.save(filepath)
        insertDb(conn, cursor, filepath, experiment_id, metadata)
    conn.close()


def connectDb():
    connection = psycopg2.connect(database="drone_pilot",
                                  host="localhost",
                                  user="admin",
                                  password="password",
                                  port="5432")
    return connection, connection.cursor()


def insertDb(conn, cursor, file_location, experiment_id, metadata):
    # conn, cursor = connectDb()
    try:
        cursor.execute(
            f"""insert into file_information(experiment_id,file_location, metadata) 
            values('{experiment_id}','{file_location}', '{metadata}');""")
        conn.commit()
    except Exception as e:
        print(e)
