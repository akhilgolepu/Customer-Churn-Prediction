FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Tells Python to search the root /app directory for shared modules like 'model'
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install only what the API needs at runtime (the full dev/MLOps lock is requirements.txt)
COPY requirements-runtime.txt .
RUN pip install --no-cache-dir -r requirements-runtime.txt

# Copy the backend code into the container
COPY backend/ /app/backend/

# ─── INCLUDE RUNTIME ML UTILITIES ────────────────────────
COPY model/ /app/model/

EXPOSE 8000

# Platforms such as Render inject PORT; default to 8000 for docker compose / local use.
CMD ["sh", "-c", "python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]