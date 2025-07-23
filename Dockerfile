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

# This tells Render which port the container is listening on.
# Render will set this environment variable for us.
EXPOSE ${PORT}

# The command to run when the container starts.
# It now correctly uses the $PORT variable provided by Render's environment.
CMD ["gunicorn", "--timeout", "300", "--workers", "1", "--threads", "4", "-b", "0.0.0.0:${PORT}", "app:app"]
