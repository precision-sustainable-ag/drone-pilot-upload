#! /usr/local/apps/miniconda20230420/bin/python3
import glob               # use module to count files given an extension
import subprocess         # to execute linux command better than os.sys because executed command is returned
import json               # use to parse the json.log file in ../code/json.log
import os

# Algorithm
# 1- get flight information from database
#    - 1.1 save information in an array/dictionary
# 2- use flight ID to grap path to the flight folder
# 3- get image extension from db and use it to count images in fligth folder on OIT storage
# 4- Compare the number of images from db to the image count from -3-
#    - 4.1 if # images from db == # images from OIT storage
#         - 4.1.1 generate the lsf script
#         - 4.1.2 submit job the to gpu queue
# 5 - check folder/file in output_dir/code to establish job status
#     - 5.1 job completed if report found
#           - 5.1.1 move computation product to designated folder
#     - 5.2 job failed if no report found
#           - 5.2.1 consult error output and fix the issue to then resubmit the job
# 6 - Monitor running jobs
#   - 6.1 input job status in db.

## Set global variables
## Read flight information from database
UUID="93238409-1871-4b81-bd25-cf0c26f50c9c"  # this is a unique identifier
ROOT_DIR="/rs1/shares/cals-research-station/sandhills/transfer/"
RELATIVE_IMAGEDIR="benchmark/0004SET/images"      # this is relative to the root directory
RAW_IMAGE_DIR=ROOT_DIR + RELATIVE_IMAGEDIR
jobID=""                           # Initialize job id after submission
                                      # to lsf scheduler

## Set variables for the LSF submission scripts
JOB_RUNTIME_1="25:00"  # 25 hours and zero minutes
JOB_NAME_23=UUID
SCRATCH_DIR_4="/share/hpc-support/jfossot/tmp"
RELATIVE_OUTPUTDIR="benchmark/HPC/testcron"
RELATIVE_IMAGEDIR="benchmark/0004SET/images"
OUTPUT_DIR_5=ROOT_DIR + RELATIVE_OUTPUTDIR
IMAGE_DIR_6=ROOT_DIR + RELATIVE_IMAGEDIR
# the path to the singularity image file (SIF) should be relative
# to the output directory
# RELATIVE_SIF_PATH="benchmark/HPC/gpu/odm_gpu.sif"
PATH_2_SIF_7="../gpu/odm_gpu.sif"

## define LSF submission script template
#
lsfTemplate='''#!/bin/bash
#BSUB -n 8
## requested job run time
#BSUB -W %s
#BSUB -q gpu
#BSUB -R "select[ a100 || a10 || a30 ]"
#BSUB -gpu "num=1:mode=shared:mps=no"
## Tag general output file and std error output
#BSUB -o out-gpu.%s
#BSUB -e err-gpu.%s
export tmp_dir='%s'
export output_dir='%s'
export images_dir='%s'
mkdir -p $output_dir/code/images
cp $images_dir/* $output_dir/code/images
# specify --nv to invoke NVidia cuda library inside the container
# more here https://github.com/sylabs/singularity-userdocs/blob/main/gpu.rst
singularity run --bind $output_dir/code/images,$tmp_dir --writable-tmpfs --nv %s \
--feature-quality ultra --min-num-features 50000 --project-path $output_dir --dsm --dtm
'''

## Function to count number images in the folder,
# using the image extension
def countImages(path,imgExt):
    print(f'\n Counting images in the OIT storage')
    try:
        countImages = len(glob.glob1(path, "*.%s"%imgExt))
        print(f' \n Counted {countImages} images \n')
    except Exception as e:
        print('except ', e)
    return countImages

## function to submit lsf job on Hazel cluster
def submitJob(lsfscript):
    # use python subprocess to execute linux command and collect the output
    # returned as A CLASS object formated as string
    try:
        result = subprocess.run(["bsub < %s"%(lsfscript)], shell=True, capture_output=True, text=True)
        jobid = result.stdout.split('>')[0].split('<')[1]
    except Exception as e:
        print('except ', e)
    return jobid

def monitoreJob(jobID):
    statusList = ["RUN","PEND"]
    status ="RUN"
    print(f"\n Job with id {jobID} is being monitored \n")
    try:
        while status in statusList:
            result = subprocess.run(["bjobs -r %d "%(jobID)], shell=True, capture_output=True, text=True)
            if len(result.stdout.split())>10:
                status = result.stdout.split()[10]
                if status=="RUN":
                    #print("Job %d is  running"%jobID)
                    pass
                elif status=="PEND": 
                    print(f"Job {jobID} is pending. Status {status}\n")
                else:
                    pass
        result = subprocess.run(["bjobs -r %d "%(jobID)], shell=True, capture_output=True, text=True)
        if len(result.stdout.split())<10:
            print(f"Job {jobID} is no longer running, Status: {status}")
        else:
            print(f"Job {jobID} is no longer running, Status: {status}")
    except Exception as e:
        print('except ', e)
    return status

## Generate lsf submission script
#
def generateLsfScript(UUID):
    try:
        lsfScriptName="%s-lsf.sh"%UUID
        f = open(lsfScriptName, "w")
        f.write(lsfTemplate%(JOB_RUNTIME_1,JOB_NAME_23,JOB_NAME_23,SCRATCH_DIR_4,OUTPUT_DIR_5,IMAGE_DIR_6,PATH_2_SIF_7))
        f.close()
        print(f' LSF submission script written in file {lsfScriptName} \n')
    except Exception as e:
        print('except ', e)
    return lsfScriptName

# How do you determine the job is completed? lsf bjobs?

# After job is completed extract completion status and other information
def parseJsonLogFile(key):
    try:
        fobj = open('%s/code/log.json'%OUTPUT_DIR_5,'r')
        pdictionary = json.loads(fobj.read())
        value=pdictionary[key]
        #True
        print(f' The value of {key} is {value} \n')
        #print(pdictionary["endTime"])
        #2024-06-12T18:13:54.654246
        #print(pdictionary["totalTime"])
        #71858.15
        fobj.close()
    except Exception as e:
        print('except ', e)
    return value

## main to call an execute auxillary functions
#
def main():
    # Get number of images uploaded to the database
    numberOfImages=13355                  
    # count images in the flight folder on OIT storage
    imgExt='tif'
    path=RAW_IMAGE_DIR
    countedImages=countImages(path,imgExt)
    if numberOfImages==countedImages:
        # Generate LSF submission files
        lsfscript=generateLsfScript(UUID)
        # submit job to lsf scheduler and get the job ID
        jobID=int(submitJob(lsfscript))
        print(f' Job has been submitted to the Hazel HPC with ID {jobID}\n')
    #Monitor job
    status =""
    status=monitoreJob(jobID)
    # check to see if job has completed successfuly or if it has failed
    # if job is successful then the log.json exist if not it doesn't
    # Verify that log.json exist
    #print(f"Job with id {jobID} has status {status}\n")
    if status=="EXIT": 
        print(f"Job with id {jobID} did not complete successfully")
    else:
        codePath = OUTPUT_DIR_5 + "/code"
        files = [f for f in os.listdir(codePath) if os.path.isfile(os.path.join(codePath,f))]
        for f in files:
            if f=="log.json":
                jobStatus=parseJsonLogFile("success")
                jobEndTime=parseJsonLogFile("endTime")
                jobTotalTime=parseJsonLogFile("totalTime")
                print(f"{jobID} completed at {jobEndTime} running for {jobTotalTime} secs")

    return None

if __name__ == '__main__':
    main()
