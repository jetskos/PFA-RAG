# Use an official lightweight Python image
FROM python:3.11-slim

# Set environment variables to prevent Python from writing pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies required for mysqlclient, chromadb, and other build tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    default-libmysqlclient-dev \
    pkg-config \
    libmariadb-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
# Force CPU-only ONNX runtime to prevent CUDA provider SIGSEGV in Docker.
# Install a stable version of onnxruntime (1.15.1) to avoid SIGSEGV in newer kernels
RUN pip install --no-cache-dir --force-reinstall "onnxruntime==1.15.1"

# Copy the entire Django project into the container
COPY . /app/

# Expose port 8000 for the Django web server
EXPOSE 8000

# Collect static files for production
RUN python manage.py collectstatic --noinput

# Start the custom shell script which runs both Celery (with concurrency=1) and Daphne
CMD ["bash", "start.sh"]
