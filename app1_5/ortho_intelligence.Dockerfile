# FROM ghcr.io/osgeo/gdal:alpine-small-3.8.4

# # RUN apt-get clean \
# #     && apt-get update --fix-missing \
# #     && apt-get install -y

# # RUN apt-get install -y libgdal-dev locales

# # # Ensure locales configured correctly
# # RUN locale-gen en_GB.UTF-8
# # ENV LC_ALL='en_GB.utf8'

# # # Set python aliases for python3
# # RUN echo 'alias python=python3' >> ~/.bashrc
# # RUN echo 'alias pip=pip3' >> ~/.bashrc

# # # Update C env vars so compiler can find gdal
# # ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
# # ENV C_INCLUDE_PATH=/usr/include/gdal

# # # This will install latest version of GDAL
# # RUN pip install GDAL
# RUN apk add python3
# RUN apk add py3-pip

FROM python:3.8-slim

# Install system dependencies for GDAL
RUN apt-get update \
    && apt-get install -y \
        libgdal-dev \
        gdal-bin \
        python3-gdal \
    && rm -rf /var/lib/apt/lists/*

# Install Rasterio and any other Python dependencies
RUN pip install rasterio

# RUN pip3 install rasterio numpy

WORKDIR /code
COPY ortho_intelligence.py .


ENTRYPOINT ["python3", "/code/ortho_intelligence.py"]
