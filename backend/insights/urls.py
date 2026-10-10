from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('simulator', views.SimulatorView.as_view(), name='simulator'),
    path('health', views.HealthView.as_view(), name='club-health'),
    path('savefiles', views.SaveFileListCreateView.as_view(), name='savefile-list'),
]
