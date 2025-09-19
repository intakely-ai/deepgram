# syntax=docker/dockerfile:1.7
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy project
COPY . /app

# Install Python deps if requirements.txt exists
RUN --mount=type=cache,target=/root/.cache/pip \
    if [ -f requirements.txt ]; then pip install -r requirements.txt; else echo "No requirements.txt; skipping pip install."; fi

EXPOSE 5000 8000
CMD ["python", "--version"]
