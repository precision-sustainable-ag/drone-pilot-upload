sudo apt -y install nodejs npm git nginx
python3 -m pip install --user virtualenv

cd /var/www/
sudo git clone https://github.com/precision-sustainable-ag/drone-pilot-upload.git

cd /var/www/drone-pilot-upload/frontend
npm run build

sudo rm -rf /etc/nginx/sites-enabled/default
sudo rm -rf /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo cp /var/www/drone-pilot-upload/frontend/prod.nginx /etc/nginx/sites-available/drone_pilot_upload.nginx
sudo ln -s /etc/nginx/sites-available/drone_pilot_upload.nginx /etc/nginx/sites-enabled/drone_pilot_upload.nginx

sudo systemctl reload nginx
