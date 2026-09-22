"""Shared budget/cost math — used by the Project Summary budget panel and the Time Reports
'Budget vs Actual' mode, so both read from the exact same effective-cost computation."""
from decimal import Decimal

from django.db.models import Sum

from .models import BillableRate, TimeEntry


def resolve_hourly_rate(user_id, project_id) -> Decimal:
    """Priority: a user-scoped override, then a project-scoped override, then the
    organization default. Falls back to 0 if nothing is configured at all."""
    rate = BillableRate.objects.filter(scope=BillableRate.Scope.USER, user_id=user_id).first()
    if rate:
        return rate.hourly_rate
    rate = BillableRate.objects.filter(scope=BillableRate.Scope.PROJECT, project_id=project_id).first()
    if rate:
        return rate.hourly_rate
    rate = BillableRate.objects.filter(scope=BillableRate.Scope.ORGANIZATION).first()
    if rate:
        return rate.hourly_rate
    return Decimal("0")


def project_effective_cost(project_id) -> Decimal:
    """Sum of each billable TimeEntry's duration × the rate that applies to it. Only billable
    entries count toward cost — non-billable time (internal meetings, etc.) doesn't bill out."""
    entries = TimeEntry.objects.filter(project_id=project_id, is_billable=True).exclude(duration__isnull=True)
    total = Decimal("0")
    # Rates are per-user (or per-project/org fallback), so group by user to avoid re-resolving
    # the same rate on every single entry.
    by_user: dict[int, Decimal] = {}
    for entry in entries.only("user_id", "duration"):
        if entry.user_id not in by_user:
            by_user[entry.user_id] = resolve_hourly_rate(entry.user_id, project_id)
        hours = Decimal(entry.duration.total_seconds()) / Decimal(3600)
        total += hours * by_user[entry.user_id]
    return total.quantize(Decimal("0.01"))


def project_actual_hours(project_id) -> float:
    total = TimeEntry.objects.filter(project_id=project_id).exclude(duration__isnull=True).aggregate(
        total=Sum("duration")
    )["total"]
    return round(total.total_seconds() / 3600, 2) if total else 0.0


def issue_actual_hours(issue_id) -> float:
    total = TimeEntry.objects.filter(issue_id=issue_id).exclude(duration__isnull=True).aggregate(
        total=Sum("duration")
    )["total"]
    return round(total.total_seconds() / 3600, 2) if total else 0.0
