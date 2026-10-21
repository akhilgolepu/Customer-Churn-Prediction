FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Tells Python to search the root /app directory for shared modules like 'model'
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# One dependency file for the image, CI and development: the image runs exactly what the tests ran.
COPY requirements.txt .
# pip is not needed at runtime; removing it also drops the certifi copy it vendors
# (flagged CRITICAL by the image scan, GHSA-6q48-6c7w-9gw2).
RUN pip install --no-cache-dir -r requirements.txt && pip uninstall -y pip

# Copy the backend code into the container
COPY backend/ /app/backend/

# ─── INCLUDE RUNTIME ML UTILITIES ────────────────────────
COPY ml/ /app/ml/

# Trained artifacts (versioned in git, produced by `dvc repro`)
COPY models/ /app/models/

EXPOSE 8000

# Platforms such as Render inject PORT; default to 8000 for docker compose / local use.
CMD ["sh", "-c", "python -m uvicorn app:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}"]