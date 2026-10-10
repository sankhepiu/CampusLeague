from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('announcements', views.AnnouncementListCreateView.as_view(), name='announcement-list'),
    path('announcements/<int:pk>', views.AnnouncementDetailView.as_view(), name='announcement-detail'),
    path('announcements/<int:pk>/deliveries', views.DeliveryListView.as_view(), name='announcement-deliveries'),
]
