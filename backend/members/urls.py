from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('plans', views.PlanListView.as_view(), name='plan-list'),
    path('memberships', views.MembershipPurchaseView.as_view(), name='membership-purchase'),
    path('memberships/me', views.MyMembershipView.as_view(), name='membership-me'),
]
