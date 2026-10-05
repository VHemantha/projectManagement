#!/usr/bin/env bash
# Sets up and (re)starts the AI pre-check agent on the EC2 instance. Called by
# server_deploy.sh on every deploy, as root. Safe to re-run.
#
#   precheck_deploy.sh prepare <release_dir>   settings, database, Python packages
#   precheck_deploy.sh start   <release_dir>   systemd unit, restart, health check
#
# On the server:
#   /srv/trackflow/precheck-venv                      the agent's own virtualenv
#   /srv/trackflow/shared/precheck.env                its settings and secrets (root:trackflow 640)
#   /srv/trackflow/shared/precheck-google-key.json    the Google service account key (same mode)
#   database "trackflow_precheck" with the pgvector extension, on the app's Postgres
#
# A problem here never takes the main app down: server_deploy.sh treats it as a warning.
set -euo pipefail

STEP="${1:?usage: precheck_deploy.sh prepare|start <release_dir>}"
RELEASE_DIR="${2:?usage: precheck_deploy.sh prepare|start <release_dir>}"
APP_ROOT=/srv/trackflow
SHARED="$APP_ROOT/shared"
ENV_FILE="$SHARED/.env"
PC_ENV="$SHARED/precheck.env"
PC_VENV="$APP_ROOT/precheck-venv"
PC_DB=trackflow_precheck
GOOGLE_KEY="$SHARED/precheck-google-key.json"
AGENT_DIR="$RELEASE_DIR/precheck-agent"

log() { echo "==> [pre-check] $*"; }
env_get() { grep -E "^$2=" "$1" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }
env_set() { # file key value   (keeps owner and mode)
  local tmp
  tmp="$(mktemp)"
  grep -vE "^$2=" "$1" > "$tmp" || true
  printf '%s=%s\n' "$2" "$3" >> "$tmp"
  cat "$tmp" > "$1"
  rm -f "$tmp"
}

prepare() {
  # --- settings: created once, never overwritten (secrets are added with set_precheck_secrets.sh)
  if [ ! -f "$PC_ENV" ]; then
    log "Creating $PC_ENV"
    install -m 640 -o root -g trackflow /dev/null "$PC_ENV"
    token="$(python3 -c 'import secrets; print(secrets.token_urlsafe(40))')"
    cat > "$PC_ENV" <<EOF
PRECHECK_PM_BASE_URL=http://127.0.0.1:8000
PRECHECK_SERVICE_TOKEN=$token
PRECHECK_LLM_MODE=anthropic
PRECHECK_ANTHROPIC_API_KEY=
PRECHECK_PRECHECK_MODEL=claude-opus-5-5
PRECHECK_READER_MODEL=claude-haiku-4-5-20251001
PRECHECK_JUDGE_MODEL=claude-sonnet-5-5
PRECHECK_DRIVE_MODE=google
PRECHECK_GOOGLE_SERVICE_ACCOUNT_FILE=$GOOGLE_KEY
PRECHECK_BUDGET_IMAGE_CALLS=10
PRECHECK_RUN_INPUT_TOKENS=120000
PRECHECK_RUN_OUTPUT_TOKENS=24000
EOF
  fi
  chown root:trackflow "$PC_ENV"
  chmod 640 "$PC_ENV"

  # The PM application and the agent share one token and know where the other is.
  env_set "$ENV_FILE" PRECHECK_SERVICE_TOKEN "$(env_get "$PC_ENV" PRECHECK_SERVICE_TOKEN)"
  env_set "$ENV_FILE" PRECHECK_AGENT_URL "http://127.0.0.1:8100"

  # --- database: its own database on the app's Postgres, with pgvector
  db_host="$(env_get "$ENV_FILE" DB_HOST)"
  db_port="$(env_get "$ENV_FILE" DB_PORT)"
  db_user="$(env_get "$ENV_FILE" DB_USER)"
  db_pass="$(env_get "$ENV_FILE" DB_PASSWORD)"
  if [ "$db_host" = "localhost" ] || [ "$db_host" = "127.0.0.1" ]; then
    pg_major="$(sudo -u postgres psql -tAc 'show server_version_num' | cut -c1-2)"
    if ! dpkg -s "postgresql-$pg_major-pgvector" > /dev/null 2>&1; then
      log "Installing pgvector for PostgreSQL $pg_major"
      DEBIAN_FRONTEND=noninteractive apt-get update -qq
      DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "postgresql-$pg_major-pgvector"
    fi
    cd /tmp
    sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$PC_DB'" | grep -q 1 \
      || sudo -u postgres createdb -O "$db_user" "$PC_DB"
    sudo -u postgres psql -v ON_ERROR_STOP=1 -q -d "$PC_DB" -c "CREATE EXTENSION IF NOT EXISTS vector"
  else
    # RDS: the app's user is the master user, which may create databases and extensions.
    export PGPASSWORD="$db_pass"
    psql -h "$db_host" -p "$db_port" -U "$db_user" -d "$(env_get "$ENV_FILE" DB_NAME)" -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$PC_DB'" | grep -q 1 \
      || psql -h "$db_host" -p "$db_port" -U "$db_user" -d "$(env_get "$ENV_FILE" DB_NAME)" -v ON_ERROR_STOP=1 -q -c "CREATE DATABASE $PC_DB"
    psql -h "$db_host" -p "$db_port" -U "$db_user" -d "$PC_DB" -v ON_ERROR_STOP=1 -q -c "CREATE EXTENSION IF NOT EXISTS vector"
    unset PGPASSWORD
  fi
  # Built on every deploy so a changed database password or host is picked up.
  url="$(DB_USER="$db_user" DB_PASS="$db_pass" DB_HOST="$db_host" DB_PORT="$db_port" DB_NAME="$PC_DB" python3 -c     'import os; from urllib.parse import quote; e = os.environ; print("postgresql+psycopg://%s:%s@%s:%s/%s" % (quote(e["DB_USER"], safe=""), quote(e["DB_PASS"], safe=""), e["DB_HOST"], e["DB_PORT"], e["DB_NAME"]))')"
  env_set "$PC_ENV" PRECHECK_DATABASE_URL "$url"

  # --- Python packages, in the agent's own virtualenv
  log "Installing Python dependencies"
  [ -x "$PC_VENV/bin/python" ] || python3 -m venv "$PC_VENV"
  "$PC_VENV/bin/pip" install --quiet --upgrade pip
  "$PC_VENV/bin/pip" install --quiet -r "$AGENT_DIR/requirements.txt"
  ln -sfn "$PC_ENV" "$AGENT_DIR/.env"
}

start() {
  install -m 644 "$RELEASE_DIR/deploy/ec2/trackflow-precheck.service" /etc/systemd/system/trackflow-precheck.service
  systemctl daemon-reload
  systemctl enable --quiet trackflow-precheck
  systemctl restart trackflow-precheck
  for _ in $(seq 1 30); do
    if curl -fsS -o /dev/null http://127.0.0.1:8100/healthz; then
      log "Agent is up"
      [ -n "$(env_get "$PC_ENV" PRECHECK_ANTHROPIC_API_KEY)" ] \
        || log "NOTE: no Claude API key yet. Run deploy/scripts/set_precheck_secrets.sh from your machine."
      [ -f "$GOOGLE_KEY" ] \
        || log "NOTE: no Google service account key yet. Run deploy/scripts/set_precheck_secrets.sh from your machine."
      return 0
    fi
    sleep 2
  done
  echo "Pre-check agent did not start. Recent logs:" >&2
  journalctl -u trackflow-precheck -n 40 --no-pager >&2 || true
  return 1
}

"$STEP"
