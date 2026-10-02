#!/usr/bin/env bash
# Put the AI pre-check agent's two secrets on the server: the Claude API key and the Google
# service account key. Run from your machine (Git Bash on Windows, or macOS/Linux) after the
# first deploy, and again whenever a key is rotated. Nothing is written to the repository.
#
#   SSH_KEY=~/.ssh/trackflow-key.pem ./deploy/scripts/set_precheck_secrets.sh
#
# You are asked for the Claude API key (typing is hidden; leave empty to keep the current one)
# and for the path to the Google key file (leave empty to keep the current one).
#
# Env vars:
#   SSH_KEY             (required) path to the EC2 key pair .pem
#   STACK_NAME          CloudFormation stack name (default: trackflow)
#   EC2_HOST            override the instance IP (default: read from stack outputs)
#   ANTHROPIC_API_KEY   use this instead of asking
#   GOOGLE_KEY_FILE     use this instead of asking
set -euo pipefail
export MSYS_NO_PATHCONV=1

STACK_NAME="${STACK_NAME:-trackflow}"
SSH_KEY="${SSH_KEY:?Set SSH_KEY to the path of your EC2 key pair .pem file}"

HOST="${EC2_HOST:-$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
  --query "Stacks[0].Outputs[?OutputKey=='InstancePublicIp'].OutputValue" --output text | tr -d '\r')}"
[ -n "$HOST" ] && [ "$HOST" != "None" ] || { echo "Could not read InstancePublicIp from stack $STACK_NAME" >&2; exit 1; }
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new)

API_KEY="${ANTHROPIC_API_KEY:-}"
if [ -z "$API_KEY" ]; then
  read -r -s -p "Claude API key (hidden; Enter to keep the current one): " API_KEY
  echo
fi
GOOGLE_FILE="${GOOGLE_KEY_FILE:-}"
if [ -z "$GOOGLE_FILE" ]; then
  read -r -p "Path to the Google service account .json (Enter to keep the current one): " GOOGLE_FILE
fi

if [ -n "$GOOGLE_FILE" ]; then
  [ -f "$GOOGLE_FILE" ] || { echo "No such file: $GOOGLE_FILE" >&2; exit 1; }
  grep -q '"client_email"' "$GOOGLE_FILE" || { echo "That does not look like a service account key." >&2; exit 1; }
  echo "==> Uploading the Google key"
  scp "${SSH_OPTS[@]}" "$GOOGLE_FILE" "ubuntu@$HOST:/tmp/precheck-google-key.json"
fi

echo "==> Updating the server"
# The whole script, with the API key inside it, travels on standard input, so the key never
# appears in a command line or a log on either machine.
{
  printf 'api_key=%q\n' "$API_KEY"
  cat <<'REMOTE'
set -e
env=/srv/trackflow/shared/precheck.env
key=/srv/trackflow/shared/precheck-google-key.json
[ -f "$env" ] || { echo "Deploy the backend first: $env does not exist yet." >&2; exit 1; }
if [ -n "$api_key" ]; then
  tmp=$(mktemp)
  grep -v "^PRECHECK_ANTHROPIC_API_KEY=" "$env" > "$tmp" || true
  printf 'PRECHECK_ANTHROPIC_API_KEY=%s\n' "$api_key" >> "$tmp"
  cat "$tmp" > "$env"
  rm -f "$tmp"
  echo "Claude API key saved."
fi
if [ -f /tmp/precheck-google-key.json ]; then
  install -m 640 -o root -g trackflow /tmp/precheck-google-key.json "$key"
  rm -f /tmp/precheck-google-key.json
  echo "Google key saved. Share each job folder (Viewer) with:"
  python3 -c 'import json, sys; print("  " + json.load(open(sys.argv[1]))["client_email"])' "$key"
fi
systemctl restart trackflow-precheck
sleep 3
curl -fsS http://127.0.0.1:8100/healthz && echo
REMOTE
} | ssh "${SSH_OPTS[@]}" "ubuntu@$HOST" "sudo bash -s"
echo "==> Done"
