import django_filters

from .models import TimeEntry


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


class TimeEntryFilter(django_filters.FilterSet):
    user = django_filters.NumberFilter(field_name="user_id")
    user_in = NumberInFilter(field_name="user_id", lookup_expr="in")
    project = django_filters.CharFilter(field_name="project__key", lookup_expr="iexact")
    issue = django_filters.NumberFilter(field_name="issue_id")
    billable = django_filters.BooleanFilter(field_name="is_billable")
    date_from = django_filters.DateFilter(field_name="work_date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="work_date", lookup_expr="lte")

    class Meta:
        model = TimeEntry
        fields = ["user", "user_in", "project", "issue", "billable", "date_from", "date_to"]
