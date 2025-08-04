# Use an official Python runtime as a parent image
# We choose a specific version (3.11-slim-bookworm) for stability and smaller image size
FROM python:3.11-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Install system dependencies required by Playwright
# These are common dependencies for Chromium, Firefox, and WebKit
RUN apt-get update && apt-get install -y \
    libnss3 \
    libfontconfig1 \
    libdbus-1-3 \
    libatk-bridge2.0-0 \
    libxkbcommon0 \
    libdrm-amdgpu1 \
    libgbm1 \
    libgl1-mesa-glx \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf-2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libtiff-dev \
    libglib2.0-0 \
    libxrender1 \
    libxi6 \
    libxtst6 \
    libxcursor1 \
    libxext6 \
    libxft2 \
    libxinerama1 \
    libxss1 \
    libxv1 \
    libappindicator1 \
    libcurl4 \
    libsecret-1-0 \
    libvulkan1 \
    libwayland-client0 \
    libwayland-egl1 \
    libwayland-server0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libxshmfence1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libgdk-pixbuf-2.0-0 \
    libjpeg-dev \
    libpng-dev \
    libwebp-dev \
    libtiff-dev \
    libglib2.0-0 \
    libxrender1 \
    libxi6 \
    libxtst6 \
    libxcursor1 \
    libxext6 \
    libxft2 \
    libxinerama1 \
    libxss1 \
    libxv1 \
    libappindicator1 \
    libcurl4 \
    libsecret-1-0 \
    libvulkan1 \
    libwayland-client0 \
    libwayland-egl1 \
    libwayland-server0 \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
# PLAYWRIGHT_BROWSERS_PATH is set to a path within the container
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright-browsers
RUN playwright install --with-deps

# Copy the rest of your application code into the container
COPY . .

# Expose the port your app will run on
EXPOSE 5050

# Command to run the application
# Gunicorn will bind to 0.0.0.0 and use the PORT environment variable provided by Render
CMD gunicorn --worker-class gevent --bind 0.0.0.0:$PORT app:app