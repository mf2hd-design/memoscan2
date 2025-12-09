FROM python:3.11-slim-bookworm

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libnss3 libfontconfig1 libdbus-1-3 libatk-bridge2.0-0 libxkbcommon0 \
    libdrm2 libgbm1 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
    libasound2 libatspi2.0-0 libgtk-3-0 libgdk-pixbuf2.0-0 \
    curl postgresql-client \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
ENV PLAYWRIGHT_BROWSERS_PATH=/playwright-browsers
RUN playwright install --with-deps chromium

# Copy application
COPY . .

# Create cache directory
RUN mkdir -p /tmp/sbf_cache

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
