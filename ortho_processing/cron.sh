#!/bin/bash
#export TMPDIR="/share/psi/jbshah/tmp"
export LSF_SERVERDIR="/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/etc"
#export TEMP="/share/psi/jbshah/tmp"
export MODULES_RUN_QUARANTINE="LD_LIBRARY_PATH LD_PRELOAD"
#export APPTAINER_CACHEDIR="/share/psi/jbshah/tmp"
export LSF_LIBDIR="/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/lib"
export LD_LIBRARY_PATH="/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/lib"
export LSF_BINDIR="/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/bin"
#export TMP="/share/psi/jbshah/tmp"
export LSF_ENVDIR="/usr/local/lsf/conf"
#export PATH=/usr/local/apps/apptainer/1.2.2-1/bin:/usr/share/Modules/bin:/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/etc:/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/usr/lpp/mmfs/bin:/home/jbshah/.local/bin:/home/jbshah/bin
export PATH=/usr/local/apps/apptainer/1.2.2-1/bin:/usr/share/Modules/bin:/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/etc:/usr/local/lsf/10.1/linux3.10-glibc2.17-x86_64/bin:/usr/local/bin:/usr/bin:/usr/local/sbin:/usr/sbin:/usr/lpp/mmfs/bin
#python3 -c "import os; print(os.environ)"

#cd /rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/
# cd /rs1/shares/cals-research-station/virtual/
# /rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/venv/bin/python3 /rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/ortho_processing/cron.py >> /rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/jinam_cron.log 2>&1
#/rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/venv/bin/python3 /rs1/shares/cals-research-station/sandhills/transfer/benchmark/HPC/testcron/ortho_processing/cron.py
# /rs1/shares/cals-research-station/virtual/software/app1_5/venv/bin/python3 /rs1/shares/cals-research-station/virtual/software/app1_5/drone-pilot-upload/ortho_processing/cron.py
/usr/local/usrapps/drones/drone-pilot-upload/backend/venv/bin/python3 /usr/local/usrapps/drones/drone-pilot-upload/ortho_processing/cron.py
