from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('audit', views.AuditLogListView.as_view(), name='audit-list'),
]
