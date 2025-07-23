# Use an official, slim Python image.
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED True

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# This line is primarily for documentation; the CMD line is what matters for execution.
EXPOSE 10000

#
# --- THE FIX IS HERE ---
# We now use the 'shell' form of CMD, which correctly processes the ${PORT} environment variable.
#
CMD gunicorn --timeout 300 --workers 1 --threads 4 -b 0.0.0.0:${PORT} app:app
