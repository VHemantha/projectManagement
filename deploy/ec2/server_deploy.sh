#!/usr/bin/env bash
# Runs ON the EC2 instance, as root, for every backend deploy (called by
# deploy/scripts/deploy_backend.sh). Safe to re-run.
#
# Usage: server_deploy.sh <release_dir> [comma-separated public hostnames]
#
# Layout on the server:
#   /srv/trackflow/releases/<id>/   extracted release (backend/ + deploy/ec2/)
#   /srv/trackflow/current          symlink -> active release
#   /srv/trackflow/venv             shared virtualenv
#   /srv/trackflow/precheck-venv    the AI pre-check agent's virtualenv (see precheck_deploy.sh)
#   /srv/trackflow/shared/.env      secrets/config (written at first boot)
#   /srv/trackflow/shared/{media,static,backups}
set -euo pipefail

RELEASE_DIR="${1:?usage: server_deploy.sh <release_dir> [domains]}"
APP_DOMAINS="${2:-}"
APP_ROOT=/srv/trackflow
SHARED="$APP_ROOT/shared"
ENV_FILE="$SHARED/.env"
VENV="$APP_ROOT/venv"
DEPLOY_DIR="$RELEASE_DIR/deploy/ec2"
KEEP_RELEASES=5

log() { echo "==> $*"; }

env_get() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }
env_set() {
  local tmp
  tmp="$(mktemp)"
  grep -vE "^$1=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$ENV_FILE" # `cat >` keeps the file's owner and mode
  rm -f "$tmp"
}

log "Waiting for first-boot provisioning (cloud-init) to finish"
cloud-init status --wait > /dev/null || true
if [ ! -f "$ENV_FILE" ]; then
  echo "Missing $ENV_FILE: first-boot provisioning failed. See /var/log/cloud-init-output.log" >&2
  exit 1
fi

if [ -n "$APP_DOMAINS" ]; then
  log "Allowing hosts: $APP_DOMAINS"
  origins="$(echo "$APP_DOMAINS" | tr ',' '\n' | sed 's#^#https://#' | paste -sd, -)"
  env_set ALLOWED_HOSTS "$APP_DOMAINS,localhost,127.0.0.1"
  env_set CSRF_TRUSTED_ORIGINS "$origins"
  env_set CORS_ALLOWED_ORIGINS "$origins"
fi
chown root:trackflow "$ENV_FILE"
chmod 640 "$ENV_FILE"

log "Installing Python dependencies"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$RELEASE_DIR/backend/requirements.txt"

# AI pre-check agent (settings, database, packages). It sets PRECHECK_* in the app's .env, so
# it runs before the app restarts. A problem here must not stop the main app from deploying.
PRECHECK_OK=0
if [ -d "$RELEASE_DIR/precheck-agent" ]; then
  if bash "$DEPLOY_DIR/precheck_deploy.sh" prepare "$RELEASE_DIR"; then
    PRECHECK_OK=1
  else
    echo "WARNING: could not prepare the AI pre-check agent; the main app will still deploy." >&2
  fi
fi

ln -sfn "$ENV_FILE" "$RELEASE_DIR/backend/.env"
chmod -R a+rX "$RELEASE_DIR"

manage() { (cd "$RELEASE_DIR/backend" && sudo -u trackflow "$VENV/bin/python" manage.py "$@"); }

log "Running database migrations"
manage migrate --noinput
manage bootstrap

log "Collecting static files"
manage collectstatic --noinput --verbosity 0

log "Installing nginx, systemd, backup and helper config"
secret="$(env_get ORIGIN_SECRET)"
sed "s|__ORIGIN_SECRET__|$secret|g" "$DEPLOY_DIR/nginx.conf" > /etc/nginx/sites-available/trackflow
ln -sfn /etc/nginx/sites-available/trackflow /etc/nginx/sites-enabled/trackflow
rm -f /etc/nginx/sites-enabled/default
nginx -t
install -m 644 "$DEPLOY_DIR/trackflow.service" /etc/systemd/system/trackflow.service
install -m 755 "$DEPLOY_DIR/backup_db.sh" /usr/local/bin/trackflow-backup
install -m 755 "$DEPLOY_DIR/trackflow-manage.sh" /usr/local/bin/trackflow-manage
echo '30 3 * * * root /usr/local/bin/trackflow-backup >> /var/log/trackflow-backup.log 2>&1' \
  > /etc/cron.d/trackflow-backup
systemctl daemon-reload
systemctl enable --quiet trackflow

log "Activating release $(basename "$RELEASE_DIR")"
ln -sfn "$RELEASE_DIR" "$APP_ROOT/current.tmp"
mv -Tf "$APP_ROOT/current.tmp" "$APP_ROOT/current"
systemctl restart trackflow
systemctl reload nginx

log "Health check"
healthy=0
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null -H "Host: localhost" -H "X-Origin-Verify: $secret" \
      http://127.0.0.1/api/health/; then
    healthy=1
    break
  fi
  sleep 2
done
if [ "$healthy" != 1 ]; then
  echo "Health check FAILED. Recent app logs:" >&2
  journalctl -u trackflow -n 60 --no-pager >&2 || true
  exit 1
fi

if [ "$PRECHECK_OK" = 1 ]; then
  bash "$DEPLOY_DIR/precheck_deploy.sh" start "$RELEASE_DIR"     || echo "WARNING: the AI pre-check agent is not running; the rest of the app is live." >&2
fi

log "Pruning old releases (keeping $KEEP_RELEASES)"
ls -1dt "$APP_ROOT"/releases/*/ | tail -n +$((KEEP_RELEASES + 1)) | xargs -r rm -rf

log "Deploy complete: $(basename "$RELEASE_DIR")"
