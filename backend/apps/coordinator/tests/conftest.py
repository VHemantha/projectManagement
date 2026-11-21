import pytest


@pytest.fixture(autouse=True)
def _no_low_hours_note(settings):
    """The daily low-hours note (low_hours.py) has its own tests; the other tests count every message
    sent, so it is switched off for them."""
    settings.COORDINATOR_LOW_HOURS = False
