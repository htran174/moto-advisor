# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Make Python behave nicely in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Minimal system deps (kept tiny)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first (layer cache)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the app last
COPY . .

# Expose Flask port
EXPOSE 5000

# Start with Gunicorn (production-ish)
# -w 2: two worker processes
# -k gthread + --threads 4: thread-per-conn; good for I/O-bound Flask apps
# --timeout 60: avoid zombie workers on slow external calls
CMD ["gunicorn", "-w", "2", "-k", "gthread", "--threads", "4", "--timeout", "60", "-b", "0.0.0.0:5000", "app:app"]
