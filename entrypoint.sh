#!/bin/sh
set -e

# Export the container env into a file cron's jobs can source, since cron
# runs with a minimal environment.
printenv | grep -E '^(ANTHROPIC_|ADVISOR_|SMTP_|EMAIL_|KITE_|UPSTOX_|ANGEL_|TZ|DATABASE_URL|API_SECRET_KEY|SECRETS_ENC_KEY|ACCESS_TOKEN_|REFRESH_TOKEN_|GOOGLE_|FRONTEND_URL|ALLOW_REGISTRATION|CORS_ORIGINS)=' \
  | sed 's/^\([^=]*\)=\(.*\)$/export \1='"'"'\2'"'"'/' > /app/.cron_env || true

cat > /app/run_session.sh <<'EOF'
#!/bin/sh
. /app/.cron_env
cd /app && exec python -m advisor "$@"
EOF
chmod +x /app/run_session.sh

# Rewrite crontab to go through the env-loading wrapper.
sed 's#python -m advisor#/app/run_session.sh#g' /app/crontab | crontab -

echo "advisor: cron installed, waiting for scheduled sessions (TZ=$TZ)"
exec cron -f
