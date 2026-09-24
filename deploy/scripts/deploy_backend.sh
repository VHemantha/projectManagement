#!/usr/bin/env bash
# Deploy the Django backend to the EC2 instance created by the CloudFormation stack.
# Runs from your machine (Git Bash on Windows, or macOS/Linux) or from GitHub Actions.
#
#   SSH_KEY=~/.ssh/trackflow-key.pem ./deploy/scripts/deploy_backend.sh
#
# Env vars:
#   SSH_KEY      (required) path to the EC2 key pair .pem
#   STACK_NAME   CloudFormation stack name (default: trackflow)
#   GIT_REF      commit/branch to deploy (default: HEAD). Only COMMITTED code is shipped.
#   EC2_HOST     override the instance IP (default: read from stack outputs)
#   APP_DOMAINS  override allowed hostnames (default: read from stack outputs)
set -euo pipefail
export MSYS_NO_PATHCONV=1 # stop Git Bash rewriting /remote/paths into C:/Program Files/Git/...

STACK_NAME="${STACK_NAME:-trackflow}"
GIT_REF="${GIT_REF:-HEAD}"
SSH_KEY="${SSH_KEY:?Set SSH_KEY to the path of your EC2 key pair .pem file}"

cd "$(git rev-parse --show-toplevel)"

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text | tr -d '\r'
}

HOST="${EC2_HOST:-$(stack_output InstancePublicIp)}"
DOMAINS="${APP_DOMAINS:-$(stack_output AppDomains)}"
[ -n "$HOST" ] && [ "$HOST" != "None" ] || { echo "Could not read InstancePublicIp from stack $STACK_NAME" >&2; exit 1; }

if [ "$GIT_REF" = "HEAD" ] && [ -n "$(git status --porcelain -- backend deploy/ec2)" ]; then
  echo "WARNING: uncommitted changes under backend/ or deploy/ec2/ will NOT be deployed." >&2
fi

RELEASE="$(date -u +%Y%m%d%H%M%S)-$(git rev-parse --short "$GIT_REF")"
ARCHIVE="$(mktemp -d)/trackflow-$RELEASE.tar.gz"
echo "==> Packaging $GIT_REF as release $RELEASE"
git archive --format=tar.gz -o "$ARCHIVE" "$GIT_REF" backend deploy/ec2

SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)

echo "==> Uploading to ubuntu@$HOST"
scp "${SSH_OPTS[@]}" "$ARCHIVE" "ubuntu@$HOST:/tmp/trackflow-$RELEASE.tar.gz"
rm -f "$ARCHIVE"

echo "==> Running server-side deploy"
ssh "${SSH_OPTS[@]}" "ubuntu@$HOST" "sudo bash -c '
  set -e
  dir=/srv/trackflow/releases/$RELEASE
  mkdir -p \$dir
  tar -xzf /tmp/trackflow-$RELEASE.tar.gz -C \$dir
  rm -f /tmp/trackflow-$RELEASE.tar.gz
  bash \$dir/deploy/ec2/server_deploy.sh \$dir \"$DOMAINS\"
'"
