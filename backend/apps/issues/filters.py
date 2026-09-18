import django_filters

from .models import Issue


class NumberInFilter(django_filters.BaseInFilter, django_filters.NumberFilter):
    pass


class IssueFilter(django_filters.FilterSet):
    project = django_filters.CharFilter(field_name="project__key", lookup_expr="iexact")
    project_in = django_filters.CharFilter(method="filter_project_in")
    status = django_filters.NumberFilter(field_name="status_id")
    status_category = django_filters.CharFilter(field_name="status__category")
    issue_type = django_filters.CharFilter(field_name="issue_type__name")
    exclude_type = django_filters.CharFilter(method="filter_exclude_type")
    assignee = django_filters.NumberFilter(field_name="assignee_id")
    assignee_in = NumberInFilter(field_name="assignee_id", lookup_expr="in")
    unassigned = django_filters.BooleanFilter(field_name="assignee", lookup_expr="isnull")
    reporter = django_filters.NumberFilter(field_name="reporter_id")
    sprint = django_filters.NumberFilter(field_name="sprint_id")
    no_sprint = django_filters.BooleanFilter(field_name="sprint", lookup_expr="isnull")
    epic = django_filters.NumberFilter(field_name="epic_id")
    parent = django_filters.NumberFilter(field_name="parent_id")
    no_parent = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")
    priority = django_filters.CharFilter(field_name="priority")
    label = django_filters.NumberFilter(field_name="labels__id")
    component = django_filters.NumberFilter(field_name="components__id")

    def filter_exclude_type(self, queryset, name, value):
        return queryset.exclude(issue_type__name=value)

    def filter_project_in(self, queryset, name, value):
        keys = [v.strip().upper() for v in value.split(",") if v.strip()]
        return queryset.filter(project__key__in=keys)

    class Meta:
        model = Issue
        fields = [
            "project",
            "project_in",
            "status",
            "status_category",
            "issue_type",
            "exclude_type",
            "assignee",
            "assignee_in",
            "unassigned",
            "reporter",
            "sprint",
            "no_sprint",
            "epic",
            "parent",
            "no_parent",
            "priority",
            "label",
            "component",
        ]
