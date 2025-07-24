# -------- base image --------
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---- system deps for Pillow, lxml (and a few common ones) ----
# If you ever see build errors still, temporarily add: build-essential gcc
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    libpng-dev \
    libxml2 \
    libxslt1.1 \
    ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install Python deps
RUN pip install --upgrade pip wheel \
 && pip install -r requirements.txt

# Copy the rest of the app
COPY . .

# Render injects PORT, but expose for local dev
EXPOSE 10000

# Gunicorn + gevent (matches your app)
CMD gunicorn -k gevent -b 0.0.0.0:${PORT:-10000} app:app
