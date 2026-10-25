"""One round of the coordination agent's checks. Run every 15 minutes by cron on the server:

    */15 * * * * root /usr/local/bin/trackflow-manage coordinator_tick

Checks run silently at any time; messages go out only in the messaging window. Paused: does
nothing. A run that is still going when the next is due makes the next one skip.
"""
import json
import os
import tempfile

from django.core.management.base import BaseCommand

from apps.coordinator.engine import tick


class _Lock:
    def __init__(self, path):
        self.path, self.handle = path, None

    def __enter__(self):
        try:
            import fcntl
        except ImportError:  # Windows (development): no overlap protection needed
            return True
        self.handle = open(self.path, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def __exit__(self, *exc):
        if self.handle:
            self.handle.close()


class Command(BaseCommand):
    help = "Run one round of the AI coordination agent's checks."

    def handle(self, *args, **options):
        with _Lock(os.path.join(tempfile.gettempdir(), "trackflow-coordinator.lock")) as got:
            if not got:
                self.stdout.write("Another round is still running; skipped.")
                return
            self.stdout.write(json.dumps(tick(), default=str))
