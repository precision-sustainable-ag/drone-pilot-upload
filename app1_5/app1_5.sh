#!/bin/bash

# parameters - $1
# $1 - current flight folder
# $2 - flight_id
parentdir="$(dirname "$1")"
flightdir="$1"
flight_id="$2"
# echo "$parentdir"
# echo dataset/$2

# RUN ODM
# TODO: @Jacob - change this to singularity implementation for HPC
docker run -ti --rm -v $parentdir:/dataset/ opendronemap/odm --project-path /dataset $2 --dsm --dtm --cog  --mesh-octree-depth 12 --orthophoto-compression LZMA --orthophoto-resolution 0.001 --feature-quality ultra --pc-quality ultra --min-num-features 50000 &> $1/odm.log

# CREATE COG
# TODO: @Jinam - make sure rio is installed on whichever machine runs this code
ortho_path="$flightdir""/odm_orthophoto/odm_orthophoto.tif"
cog_path="$flightdir""/odm_orthophoto/cog.tif"
rio cogeo create $ortho_path $cog_path

# CREATE VEG INDEX FILES
# TODO: @Jacob - change this to singularity implementation for HPC
docker run -it --rm -v $flightdir:/dataset/ drone_ortho_intel:latest
$cog_path $flightdir

# DB ENTRY AND CRS EXTRACTION
python3

# MONGO_HOST="localhost"
# MONGO_PORT="27017"
# DATABASE="drone-pilot"
# COLLECTION="flight-information"
# USERNAME="admin"
# PASSWORD="yolo"



# echo "$ortho_path"
# QUERY="{ \"flight_id\": \"$flight_id\" }"
# UPDATE="{\"\$set\": {\"orthomosaic_path\": \"$flightdir\"}}"
# echo "$QUERY"
# echo "$UPDATE"
# mongosh "$MONGO_HOST:$MONGO_PORT/$DATABASE" --username "$USERNAME" --password "$PASSWORD" --authenticationDatabase "admin" --eval "db.$COLLECTION.updateMany($QUERY, $UPDATE)"


