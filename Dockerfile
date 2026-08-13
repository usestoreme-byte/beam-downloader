FROM python:3.11-slim

# Install all system dependencies ONCE during build
RUN apt-get update && apt-get install -y --no-install-recommends \
    aria2 ffmpeg mkvtoolnix tesseract-ocr mediainfo git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies ONCE during build
RUN pip install --no-cache-dir telethon requests requests-toolbelt pymediainfo pgsrip

WORKDIR /app
