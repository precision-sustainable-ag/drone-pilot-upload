# MongoDB installation for Ubuntu 22.04

sudo apt-get install gnupg curl
curl -fsSL https://pgp.mongodb.com/server-7.0.asc | \
   sudo gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg \
   --dearmor

# curl -fsSL https://www.mongodb.org/static/pgp/server-4.4.asc | sudo apt-key add -
echo "deb [ arch=amd64,arm64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg ] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" | sudo tee /etc/apt/sources.list.d/mongodb-org-7.0.list

sudo apt-get update
sudo apt-get install -y mongodb-org

# Pauses updates whenever apt-get upgrade is used (prevents unexpected issues)
echo "mongodb-org hold" | sudo dpkg --set-selections
echo "mongodb-org-database hold" | sudo dpkg --set-selections
echo "mongodb-org-server hold" | sudo dpkg --set-selections
echo "mongodb-mongosh hold" | sudo dpkg --set-selections
echo "mongodb-org-mongos hold" | sudo dpkg --set-selections
echo "mongodb-org-tools hold" | sudo dpkg --set-selections

sudo systemctl daemon-reload
sudo systemctl start mongod

# update mongodb config - net.bindIp 0.0.0.0

# add authenticaton
# 
# use admin
# db.createUser(
#   {
#     user: "myUserAdmin",
#     pwd: "abc123",
#     roles: [ { role: "userAdminAnyDatabase", db: "admin" }, "dbAdminAnyDatabase", "readWriteAnyDatabase" ]
#   }
# )
# 
# add to config - security: authorization: "enabled"

# use drone-pilot
# create user with read-write only

# db['flight-information'].createIndex({flight_id:'text'}, {unique:true})