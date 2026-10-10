from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('events', views.EventListCreateView.as_view(), name='event-list'),
    path('events/<int:pk>', views.EventDetailView.as_view(), name='event-detail'),
    path('events/<int:pk>/tiers', views.TierCreateView.as_view(), name='event-tiers'),
    path('events/<int:pk>/tickets', views.TicketPurchaseView.as_view(), name='event-tickets'),
    path('events/<int:pk>/attendance', views.EventAttendanceView.as_view(), name='event-attendance'),
    path('events/<int:pk>/pnl', views.EventPnlView.as_view(), name='event-pnl'),
    path('tickets/me', views.MyTicketsView.as_view(), name='ticket-me'),
    path('tickets/passes/<int:pk>', views.PassDetailView.as_view(), name='ticket-pass'),
    path('checkin', views.CheckInView.as_view(), name='checkin'),
]
