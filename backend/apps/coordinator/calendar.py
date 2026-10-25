"""Work calendars: who is meant to work when. The timesheet and deadline rules use these, so a
person on approved leave, a public holiday or a part-time day is never warned for it."""
from datetime import date, timedelta

from .models import LeaveRecord, PublicHoliday, WorkSchedule, default_week


def week_of(user) -> list[float]:
    schedule = WorkSchedule.objects.filter(user=user).first()
    hours = schedule.hours if schedule else default_week()
    return [float(h) for h in hours] if isinstance(hours, list) and len(hours) == 7 else [float(h) for h in default_week()]


def is_holiday(day: date) -> bool:
    return PublicHoliday.objects.filter(date=day).exists()


def leave_hours(user, day: date, scheduled: float) -> float:
    """Hours of approved leave on that day (a whole day unless a part day was given)."""
    total = 0.0
    for leave in LeaveRecord.objects.filter(user=user, status=LeaveRecord.Status.APPROVED, start_date__lte=day, end_date__gte=day):
        total += scheduled if leave.hours_per_day is None else min(leave.hours_per_day, scheduled)
    return min(total, scheduled)


def expected_hours(user, day: date) -> float:
    """Hours the person is expected to record that day: their schedule, less holidays and leave."""
    scheduled = week_of(user)[day.weekday()]
    if scheduled <= 0 or is_holiday(day):
        return 0.0
    return max(scheduled - leave_hours(user, day, scheduled), 0.0)


def is_working_day(day: date, user=None) -> bool:
    if user is not None:
        return expected_hours(user, day) > 0
    return day.weekday() < 5 and not is_holiday(day)


def add_days(start: date, days: int, *, basis: str = "working", user=None) -> date:
    """`days` after `start`: working days skip weekends, holidays (and the person's leave)."""
    if basis == "calendar":
        return start + timedelta(days=days)
    day, left = start, days
    while left > 0:
        day += timedelta(days=1)
        if is_working_day(day, user):
            left -= 1
    return day


def previous_working_day(day: date, user=None) -> date | None:
    """The last day before `day` the person was meant to work (within the past three weeks)."""
    for back in range(1, 22):
        d = day - timedelta(days=back)
        if is_working_day(d, user):
            return d
    return None


# New Zealand national public holidays (Mondayised where the law says). Regional anniversary
# days differ by province: the CEO adds the one that applies.
NZ_HOLIDAYS = [
    ("2026-01-01", "New Year's Day"), ("2026-01-02", "Day after New Year's Day"), ("2026-02-06", "Waitangi Day"),
    ("2026-04-03", "Good Friday"), ("2026-04-06", "Easter Monday"), ("2026-04-27", "Anzac Day (observed)"),
    ("2026-06-01", "King's Birthday"), ("2026-07-10", "Matariki"), ("2026-10-26", "Labour Day"),
    ("2026-12-25", "Christmas Day"), ("2026-12-28", "Boxing Day (observed)"),
    ("2027-01-01", "New Year's Day"), ("2027-01-04", "Day after New Year's Day (observed)"), ("2027-02-08", "Waitangi Day (observed)"),
    ("2027-03-26", "Good Friday"), ("2027-03-29", "Easter Monday"), ("2027-04-26", "Anzac Day (observed)"),
    ("2027-06-07", "King's Birthday"), ("2027-06-25", "Matariki"), ("2027-10-25", "Labour Day"),
    ("2027-12-27", "Christmas Day (observed)"), ("2027-12-28", "Boxing Day (observed)"),
]
