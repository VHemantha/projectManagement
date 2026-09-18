from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import BillableRateListView, TimeEntryViewSet, TimeReportCsvView, TimesheetViewSet

router = SimpleRouter()
router.register("time-entries", TimeEntryViewSet, basename="time-entry")
router.register("timesheets", TimesheetViewSet, basename="timesheet")

urlpatterns = [
    path("billable-rates/", BillableRateListView.as_view(), name="billable-rate-list"),
    path("time-reports/export/", TimeReportCsvView.as_view(), name="time-report-csv"),
    path("", include(router.urls)),
]
