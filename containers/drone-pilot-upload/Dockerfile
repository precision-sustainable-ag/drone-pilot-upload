# Build the React application.
FROM node:22-bookworm-slim AS frontend

WORKDIR /src/frontend

COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/ ./

# Open OnDemand proxies the application through a dynamic /rnode/... path.
# Vite's base: './' provides relative asset URLs, while App.jsx defaults
# to the relative ./imgproc API endpoint.

RUN npm run build

# Runtime image.
FROM python:3.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-jre-headless \
        libimage-exiftool-perl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/drone-pilot-upload

COPY backend/requirements.txt backend/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip==26.2.2 \
    && python -m pip install --no-cache-dir \
        -r backend/requirements.txt

COPY backend/ backend/
COPY --from=frontend /src/frontend/build frontend/build/

WORKDIR /opt/drone-pilot-upload/backend

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --timeout 0 app:app"]
