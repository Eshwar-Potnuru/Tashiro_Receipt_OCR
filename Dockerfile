# Use Python 3.11 which still has distutils
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for OCR libraries
RUN apt-get update && apt-get install -y \
    gcc \
    tesseract-ocr \
    tesseract-ocr-jpn \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching (lightweight runtime set)
COPY requirements.txt ./requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . ./

# Copy .env file if it exists (for local development)
COPY .env* ./

# Create artifacts directory inside the app directory
RUN mkdir -p artifacts

# Create config directory for Google Vision credentials
RUN mkdir -p config

# Copy Google Vision credentials if they exist
# COPY config/google_vision_key.json* config/

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "run.py"]