#!/bin/bash

# this script will need access to the database

# parameters - $1
# $1 - current flight folder
# $2 - flight_id

parentdir="$(dirname "$1")"
flightdir="$1"
flight_id="$2"
echo 'sending status'
# TODO: @Jinam - update python being used according to the machine
/Users/jbshah/venv/test/bin/python3 utils.py $flightdir $flight_id 'processing'
#echo "$parentdir"
#echo dataset/$2
# RUN ODM
# TODO: @Jacob - change this to singularity implementation for HPC
docker run -ti --rm -v $parentdir:/dataset/ opendronemap/odm --project-path \
  /dataset $2 --dsm --dtm --cog --mesh-octree-depth 12 \
  --orthophoto-compression LZMA --orthophoto-resolution 0.001 \
  --feature-quality ultra --pc-quality ultra --min-num-features 50000 &>$1/odm.log
echo 'testing odm run'
# Test code
#docker run -ti --platform linux/amd64 --rm -v $parentdir:/dataset/ opendronemap/odm --project-path /dataset $2 --dsm --dtm --cog &> $1/odm.log

echo 'testing cog run'
# CREATE COG
# TODO: @Jinam - make sure rio is installed on whichever machine runs this code
ortho_path="$flightdir""/odm_orthophoto/odm_orthophoto.tif"
cog_path="$flightdir""/odm_orthophoto/odm_orthophoto_cog.tif"
rio cogeo create $ortho_path $cog_path

#echo "$cog_path"
#echo "$ortho_path"

# CREATE VEG INDEX FILES
# TODO: @Jacob - change this to singularity implementation for HPC
docker run -it --rm -v $flightdir:/dataset/ drone_ortho_intel:latest \
$cog_path $flightdir

# TODO: @Jinam - update python being used according to the machine
/Users/jbshah/venv/test/bin/python3 utils.py $flightdir $flight_id 'processed'
