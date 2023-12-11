sudo apt -y install nodejs npm git nginx python3-venv
# python3 -m pip install --user virtualenv

cd /var/www/
sudo rm -rf /var/www/drone-pilot-upload/
sudo git clone https://github.com/precision-sustainable-ag/drone-pilot-upload.git


cd /var/www/drone-pilot-upload/frontend
sudo npm install
sudo npm run build

sudo rm -rf /etc/nginx/sites-enabled/default
sudo rm -rf /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo cp /var/www/drone-pilot-upload/frontend/prod.nginx /etc/nginx/sites-available/drone_pilot_upload.nginx
sudo ln -s /etc/nginx/sites-available/drone_pilot_upload.nginx /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo systemctl reload nginx

sudo python3 -m venv /var/www/drone-pilot-upload/backend/venv
source /var/www/drone-pilot-upload/backend/venv/bin/activate

sudo chown -R azureuser /var/www/drone-pilot-upload/

/var/www/drone-pilot-upload/backend/venv/bin/python3 -m pip install -r /var/www/drone-pilot-upload/backend/requirements.txt

sudo cp /var/www/drone-pilot-upload/backend/gunicorn.service /etc/systemd/system/drone_upload_api.service
sudo systemctl daemon-reload
sudo systemctl start drone_upload_api
# cd /var/www/drone-pilot-upload/backend
# gunicorn -b 127.0.0.1:5000 app:app

