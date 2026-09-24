#!/usr/bin/env bash
# `manage.py` for the live release, run as the app user.
# Installed as /usr/local/bin/trackflow-manage. Example: sudo trackflow-manage createsuperuser
set -euo pipefail
cd /srv/trackflow/current/backend
exec sudo -u trackflow /srv/trackflow/venv/bin/python manage.py "$@"
