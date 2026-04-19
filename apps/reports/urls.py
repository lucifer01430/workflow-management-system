from django.urls import path

from apps.reports.views import (
    export_tasks_excel_view,
    export_tasks_pdf_view,
    report_dashboard_view,
)

app_name = "reports"

urlpatterns = [
    path("", report_dashboard_view, name="dashboard"),
    path("export/excel/", export_tasks_excel_view, name="export_excel"),
    path("export/pdf/", export_tasks_pdf_view, name="export_pdf"),
]