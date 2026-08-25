FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends xvfb && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pygame
RUN pip install --no-cache-dir pytest
