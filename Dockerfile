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

RUN chmod +x entrypoint.sh scripts/*.py \
    && crontab crontab

# Default: run cron in the foreground. Override to run a one-off session:
#   docker compose run --rm advisor python -m advisor --session premarket --dry-run
CMD ["./entrypoint.sh"]
