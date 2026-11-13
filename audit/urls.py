from django.urls import path

from audit import views

urlpatterns = [
    path("activity/", views.activity_log, name="activity_log"),
    path("activity/table/", views.activity_log_table, name="activity_log_table"),
]
