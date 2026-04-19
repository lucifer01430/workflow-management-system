from django.urls import path

from apps.tasks.views import (
    approval_inbox_view,
    approve_task_view,
    create_task_view,
    edit_task_view,
    my_tasks_view,
    reject_task_view,
    request_deadline_extension_view,
    review_extension_request_view,
    task_detail_view,
    update_task_deadline_view,
    update_task_priority_view,
    update_task_status_view,
)

app_name = "tasks"

urlpatterns = [
    path("create/", create_task_view, name="create"),
    path("edit/<int:task_id>/", edit_task_view, name="edit"),
    path("my-tasks/", my_tasks_view, name="my_tasks"),
    path("detail/<int:task_id>/", task_detail_view, name="detail"),
    path("approval-inbox/", approval_inbox_view, name="approval_inbox"),
    path("approve/<int:task_id>/", approve_task_view, name="approve"),
    path("reject/<int:task_id>/", reject_task_view, name="reject"),
    path("update-deadline/<int:task_id>/", update_task_deadline_view, name="update_deadline"),
    path("update-priority/<int:task_id>/", update_task_priority_view, name="update_priority"),
    path("update-status/<int:task_id>/", update_task_status_view, name="update_status"),
    path("request-extension/<int:task_id>/", request_deadline_extension_view, name="request_extension"),
    path("review-extension/<int:request_id>/", review_extension_request_view, name="review_extension"),
]
