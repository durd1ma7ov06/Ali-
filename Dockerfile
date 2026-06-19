FROM python:3.12-slim

WORKDIR /app

# System dependencies for audio and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    portaudio19-dev \
    libsndfile1 \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Environment
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "main.py"]
