# Use an official, slim Python image.
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Tell Render that the container will listen on port 10000
EXPOSE 10000

# The command to run when the container starts.
# We've increased the timeout to 300 seconds (5 minutes) just in case.
CMD ["gunicorn", "--timeout", "300", "-b", "0.0.0.0:10000", "app:app"]
