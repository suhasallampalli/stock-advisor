# --- Stage 1: build the React (Vite) dashboard -----------------------------
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

# --- Stage 2: the API + scheduler image, with the built UI baked in --------
FROM python:3.11-slim

ENV TZ=Asia/Kolkata \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata cron ca-certificates \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN chmod +x entrypoint.sh entrypoint.web.sh scripts/*.py \
    && crontab crontab

# Default: run cron in the foreground (used by the `scheduler` service in
# docker-compose.yml — the `api` service overrides this with plain uvicorn).
# A cloud single-service deployment (e.g. Railway) instead overrides the
# start command to ./entrypoint.web.sh, which runs cron in the background
# AND serves the API + built UI in one process. One-off session:
#   docker compose run --rm advisor python -m advisor --session premarket --dry-run
CMD ["./entrypoint.sh"]
