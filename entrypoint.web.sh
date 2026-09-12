#!/bin/sh
set -e

# Single-container mode for a hosted single-service deployment (e.g. Railway):
# runs the same cron setup as entrypoint.sh, but in the BACKGROUND, then execs
# uvicorn as the foreground process — one container serves the UI + API *and*
# fires the three scheduled briefs. For local dev, keep using docker-compose's
# two-service split (entrypoint.sh) instead; this script isn't used there.

printenv | grep -E '^(ANTHROPIC_|ADVISOR_|SMTP_|EMAIL_|KITE_|UPSTOX_|ANGEL_|TZ|DATABASE_URL|API_SECRET_KEY|SECRETS_ENC_KEY|ACCESS_TOKEN_|REFRESH_TOKEN_|GOOGLE_|FRONTEND_URL|ALLOW_REGISTRATION|CORS_ORIGINS)=' \
  | sed 's/^\([^=]*\)=\(.*\)$/export \1='"'"'\2'"'"'/' > /app/.cron_env || true

cat > /app/run_session.sh <<'EOF'
#!/bin/sh
. /app/.cron_env
cd /app && exec python -m advisor "$@"
EOF
chmod +x /app/run_session.sh

sed 's#python -m advisor#/app/run_session.sh#g' /app/crontab | crontab -

echo "advisor: cron installed (background), starting API+UI on :${PORT:-8000} (TZ=$TZ)"
cron
exec uvicorn advisor.api.main:app --host 0.0.0.0 --port "${PORT:-8000}"
