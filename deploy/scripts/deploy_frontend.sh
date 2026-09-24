#!/usr/bin/env bash
# Build the React app and publish it to the stack's S3 bucket + CloudFront.
#
#   ./deploy/scripts/deploy_frontend.sh
#
# Env vars:
#   STACK_NAME   CloudFormation stack name (default: trackflow)
#   SKIP_BUILD=1 upload the existing frontend/dist without rebuilding
set -euo pipefail
export MSYS_NO_PATHCONV=1 # stop Git Bash rewriting "/*" and "/index.html" into Windows paths

STACK_NAME="${STACK_NAME:-trackflow}"

cd "$(git rev-parse --show-toplevel)"

stack_output() {
  aws cloudformation describe-stacks --stack-name "$STACK_NAME" \
    --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text | tr -d '\r'
}

BUCKET="$(stack_output FrontendBucketName)"
DISTRIBUTION_ID="$(stack_output CloudFrontDistributionId)"
[ -n "$BUCKET" ] && [ "$BUCKET" != "None" ] || { echo "Could not read FrontendBucketName from stack $STACK_NAME" >&2; exit 1; }

if [ "${SKIP_BUILD:-}" != "1" ]; then
  echo "==> Building frontend"
  (cd frontend && npm ci && npm run build)
fi

echo "==> Uploading to s3://$BUCKET"
# Hashed bundles never change, so cache them "forever". Old bundles are deliberately NOT
# deleted: browsers still running the previous index.html may lazy-load them.
aws s3 sync frontend/dist/assets "s3://$BUCKET/assets" \
  --cache-control "public,max-age=31536000,immutable"
# Everything else (favicon, icons, ...) gets a short cache; index.html is never cached.
aws s3 sync frontend/dist "s3://$BUCKET" --delete \
  --exclude "assets/*" --exclude "index.html" \
  --cache-control "public,max-age=300"
aws s3 cp frontend/dist/index.html "s3://$BUCKET/index.html" \
  --cache-control "no-cache" --content-type "text/html; charset=utf-8"

echo "==> Invalidating CloudFront cache"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
  --paths "/*" --query "Invalidation.Id" --output text

echo "==> Frontend deployed: https://$(stack_output CloudFrontDomainName)"
