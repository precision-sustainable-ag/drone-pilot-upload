#!/bin/bash

# Exit on error
set -e

# Paths
APP_DIR="/usr/local/usrapps/drones/mspinega/drone-pilot-upload"
FRONTEND_DIR="$APP_DIR/frontend"
BACKEND_DIR="$APP_DIR/backend"
RESTART_FILE="/home/mspinega/ondemand/dev/drone-pilot-backend/tmp/restart.txt"

echo "=== Pulling latest code ==="
cd "$APP_DIR"
# git pull

echo "=== Updating frontend dependencies and building ==="
cd "$FRONTEND_DIR"
source /usr/local/apps/miniconda20240526/etc/profile.d/conda.sh
conda activate node-env
npm install
npm run build
conda deactivate

echo "=== Updating backend dependencies ==="
cd "$BACKEND_DIR"
source venv/bin/activate
pip install --upgrade -r requirements.txt
deactivate

echo "=== Triggering restart ==="
echo "Updated on $(date)" > "$RESTART_FILE"
echo "=== Deployment complete! ==="
