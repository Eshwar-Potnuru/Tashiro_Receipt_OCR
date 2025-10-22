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

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create artifacts directory
RUN mkdir -p ../artifacts

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "run.py"]