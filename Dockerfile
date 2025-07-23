# Use an official, slim Python image.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED True
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# EXPOSE is mainly for documentation; the CMD line is what matters.
EXPOSE 10000

#
# --- THE FIX ---
# Switch from the default 'sync' worker to the 'gevent' worker,
# which is designed for streaming and long-lived connections.
#
CMD gunicorn --timeout 300 -k gevent -b 0.0.0.0:${PORT} app:app
