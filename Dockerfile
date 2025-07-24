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

# Tell Render which port the container is listening on.
EXPOSE 10000

# The command to run when the container starts.
CMD gunicorn -k gevent -b 0.0.0.0:${PORT} app:app
