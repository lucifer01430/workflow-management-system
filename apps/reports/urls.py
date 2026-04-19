from django.urls import path

from apps.reports.views import report_export_csv_view, report_overview_view

app_name = "reports"

urlpatterns = [
    path("", report_overview_view, name="overview"),
    path("export/csv/", report_export_csv_view, name="export_csv"),
]
