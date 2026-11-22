#!/usr/bin/env bash
# Sets up and (re)starts Local_Tax_AI, the Local Tax workflow's AI agent (AFIT, 22 Nov 2026). Called by
# server_deploy.sh after the pre-check agent has started, as root. Safe to re-run; a problem here never takes
# the main app down.
#
#   local_tax_deploy.sh prepare <release_dir>   settings (before the app restarts, so the backend reads the token)
#   local_tax_deploy.sh start   <release_dir>   systemd unit, restart, health check
#
# On the server:
#   /srv/trackflow/shared/local-tax.env   its settings (root:trackflow 640): its own service token, and the
#                                         Claude key read from precheck.env (one key for both agents)
#   it runs from /srv/trackflow/precheck-venv (the same libraries as the pre-check agent)
set -euo pipefail

STEP="${1:?usage: local_tax_deploy.sh prepare|start <release_dir>}"
RELEASE_DIR="${2:?usage: local_tax_deploy.sh prepare|start <release_dir>}"
APP_ROOT=/srv/trackflow
SHARED="$APP_ROOT/shared"
ENV_FILE="$SHARED/.env"
LT_ENV="$SHARED/local-tax.env"
PC_ENV="$SHARED/precheck.env"
DIR="$RELEASE_DIR/local-tax-ai"

log() { echo "==> [local-tax] $*"; }
env_get() { grep -E "^$2=" "$1" 2>/dev/null | tail -n1 | cut -d= -f2- || true; }
env_set() {
  local tmp
  tmp="$(mktemp)"
  grep -vE "^$2=" "$1" > "$tmp" || true
  printf '%s=%s\n' "$2" "$3" >> "$tmp"
  cat "$tmp" > "$1"
  rm -f "$tmp"
}

[ -d "$DIR" ] || { log "No local-tax-ai in this release: skipped."; exit 0; }

if [ "$STEP" = prepare ]; then
if [ ! -f "$LT_ENV" ]; then
  log "Creating $LT_ENV"
  install -m 640 -o root -g trackflow /dev/null "$LT_ENV"
  printf 'LOCAL_TAX_AI_SERVICE_TOKEN=%s\nLOCAL_TAX_AI_LLM_MODE=anthropic\nLOCAL_TAX_AI_MODEL=claude-sonnet-5-5\nLOCAL_TAX_AI_READER_MODEL=claude-sonnet-5-5\n' \
    "$(python3 -c 'import secrets; print(secrets.token_urlsafe(40))')" > "$LT_ENV"
fi
# The Claude key: the pre-check agent's, kept in step on every deploy (set_precheck_secrets.sh sets it there).
key="$(env_get "$PC_ENV" PRECHECK_ANTHROPIC_API_KEY)"
[ -n "$key" ] && env_set "$LT_ENV" LOCAL_TAX_AI_ANTHROPIC_API_KEY "$key"
# Google Drive (read-only), for a Local client's shared folder: the pre-check's service account key, the same
# account the client shares the folder with.
gkey="$(env_get "$PC_ENV" PRECHECK_GOOGLE_SERVICE_ACCOUNT_FILE)"
[ -n "$gkey" ] && env_set "$LT_ENV" LOCAL_TAX_AI_GOOGLE_SERVICE_ACCOUNT_FILE "$gkey"
chown root:trackflow "$LT_ENV"
chmod 640 "$LT_ENV"
# The backend calls it with the same token.
env_set "$ENV_FILE" LOCAL_TAX_AI_URL "http://127.0.0.1:8300"
env_set "$ENV_FILE" LOCAL_TAX_AI_TOKEN "$(env_get "$LT_ENV" LOCAL_TAX_AI_SERVICE_TOKEN)"
ln -sfn "$LT_ENV" "$DIR/.env"
exit 0
fi

install -m 644 "$RELEASE_DIR/deploy/ec2/trackflow-local-tax.service" /etc/systemd/system/trackflow-local-tax.service
systemctl daemon-reload
systemctl enable --quiet trackflow-local-tax
systemctl restart trackflow-local-tax
for _ in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8300/healthz >/dev/null 2>&1; then
    log "Local_Tax_AI is up: $(curl -fsS http://127.0.0.1:8300/healthz)"
    exit 0
  fi
  sleep 1
done
log "Local_Tax_AI did not answer its health check"
journalctl -u trackflow-local-tax -n 40 --no-pager >&2 || true
exit 1
