#!/usr/bin/env bash
# Nightly backup (installed as /usr/local/bin/trackflow-backup, run by /etc/cron.d/trackflow-backup).
# Dumps Postgres (works for both the local DB and RDS) and archives uploaded media into
# /srv/trackflow/shared/backups, keeping 7 days. These live on the same disk as the app,
# so copy them off the server periodically (see DEPLOYMENT.md, "Backups").
set -euo pipefail

ENV_FILE=/srv/trackflow/shared/.env
DEST=/srv/trackflow/shared/backups
STAMP="$(date -u +%Y%m%d-%H%M%S)"

env_get() { grep -E "^$1=" "$ENV_FILE" | tail -n1 | cut -d= -f2-; }

mkdir -p "$DEST"
export PGPASSWORD="$(env_get DB_PASSWORD)"
pg_dump --format=custom \
  -h "$(env_get DB_HOST)" -p "$(env_get DB_PORT)" -U "$(env_get DB_USER)" "$(env_get DB_NAME)" \
  > "$DEST/db-$STAMP.dump"
tar -czf "$DEST/media-$STAMP.tar.gz" -C /srv/trackflow/shared media

find "$DEST" -type f -mtime +7 -delete
echo "$(date -u) backup ok: db-$STAMP.dump media-$STAMP.tar.gz"
