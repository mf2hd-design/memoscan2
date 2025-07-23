# Use the official Microsoft Playwright image which has all browser dependencies pre-installed.
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt .

# Install the Python packages
RUN pip install -r requirements.txt

# Copy the rest of your application code into the container
COPY . .

# Tell Render that the container will listen on port 10000
EXPOSE 10000

# The command to run when the container starts. This is a standard synchronous worker.
CMD ["gunicorn", "--timeout", "180", "-b", "0.0.0.0:10000", "app:app"]
