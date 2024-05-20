# DRONE DATA UPLOAD
This is the codebase for the upload page for drone images to create orthomosaics. The targeted deployment is at different research stations.

## Tech Stack
- **React.js:** Frontend app
- **Python:** API created using Flask
- **Material UI:** UI library
- **MongoDB:** NoSQL database

## Contributing

### Code Structure
```
drone-pilot-upload
├── backend  #contains the API code
├── frontend
│   ├── public
│   │   └── images # shared images like favicon
│   └── src # contains the one-page react code
└── ortho_processing # contains codebase to orchestrate and manage HPC-based orthomosaic processing
```

### Deployment

1. Use `run.sh` to deploy the app on a stand-alone server. Uses `gunicorn` to manage the api server and `nginx` to manage the frontend.
2. Get `.env` file (for the frontend) and the updated `config.py` file (for the backend) from Jinam.
4. Run `systemctl reload drone_upload_api` and `systemctl reload nginx`

### Local development

1. Installations needed: mongodb, git, nginx, exiftool, nodejs, npm
2. Clone repo: `git clone https://github.com/precision-sustainable-ag/drone-pilot-upload.git`
3. Frontend:
   1. Install dependencies: `cd frontend && npm install`
   2. Run `npm run start`
5. Backend:
    1. Create a python virtual environment: `python3.9 -m venv ./backend/venv`
    2. Install python dependencies: `./backend/venv/bin/python3 -m pip install -r ./backend/requirements.txt`
    3. Run `./backend/venv/bin/python3 ./backend/app.py`
