# install nodejs 20
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | sudo gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_21.x nodistro main" | sudo tee /etc/apt/sources.list.d/nodesource.list
sudo apt update
sudo apt install nodejs -y

#sudo apt -y install nodejs npm git nginx python3-venv exiftool
sudo apt -y install git nginx python3-venv exiftool
# python3 -m pip install --user virtualenv

cd /var/www/
sudo rm -rf /var/www/drone-pilot-upload/
sudo git clone https://github.com/precision-sustainable-ag/drone-pilot-upload.git


cd /var/www/drone-pilot-upload/frontend
sudo npm install
sudo npm run build

# allow for unlimited files to be open concurrently
sudo ulimit -n unlimited

sudo rm -rf /etc/nginx/sites-enabled/default
sudo rm -rf /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo cp /var/www/drone-pilot-upload/frontend/prod.nginx /etc/nginx/sites-available/drone_pilot_upload.nginx
sudo ln -s /etc/nginx/sites-available/drone_pilot_upload.nginx /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo systemctl reload nginx

sudo python3.9 -m venv /var/www/drone-pilot-upload/backend/venv
source /var/www/drone-pilot-upload/backend/venv/bin/activate

sudo chown -R root /var/www/drone-pilot-upload/

sudo /var/www/drone-pilot-upload/backend/venv/bin/python3 -m pip install -r /var/www/drone-pilot-upload/backend/requirements.txt

sudo cp /var/www/drone-pilot-upload/backend/gunicorn.service /etc/systemd/system/drone_upload_api.service
sudo systemctl daemon-reload
sudo systemctl start drone_upload_api
# cd /var/www/drone-pilot-upload/backend
# gunicorn -b 127.0.0.1:5000 app:app

# update config with correct mongodb credentials
# change axios command in App.js with the correct host IP