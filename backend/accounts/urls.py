from django.urls import path

from . import views

# Mounted at /api/auth/. No trailing slashes, matching the plan's paths.
urlpatterns = [
    path('signup', views.SignupView.as_view(), name='auth-signup'),
    path('login', views.LoginView.as_view(), name='auth-login'),
    path('logout', views.LogoutView.as_view(), name='auth-logout'),
    path('me', views.MeView.as_view(), name='auth-me'),
]
