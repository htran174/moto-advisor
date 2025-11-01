# syntax=docker/dockerfile:1
FROM python:3.13-slim

# Make Python behave nicely in containers
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps (kept minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (better caching)
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Now copy the rest of your app
COPY . .

# Flask will listen on 5000
EXPOSE 5000

# Tell Flask which file is the entrypoint
ENV FLASK_APP=app.py

# gunicorn>=22.0.0
EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD wget -qO- http://127.0.0.1:5000/ || exit 1

CMD ["gunicorn", "-w", "2", "-k", "gthread", "-b", "0.0.0.0:5000", "app:app"]
