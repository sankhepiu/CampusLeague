from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('fundraisers', views.FundraiserListCreateView.as_view(), name='fundraiser-list'),
    path('fundraisers/<int:pk>', views.FundraiserDetailView.as_view(), name='fundraiser-detail'),
    path('fundraisers/<int:pk>/sales', views.FundraiserSaleView.as_view(), name='fundraiser-sales'),
    path('tasks', views.TaskCreateView.as_view(), name='task-create'),
    path('tasks/<int:pk>', views.TaskDetailView.as_view(), name='task-detail'),
    path('tasks/<int:pk>/assign', views.TaskAssignView.as_view(), name='task-assign'),
    path('tasks/<int:pk>/status', views.TaskStatusView.as_view(), name='task-status'),
]
