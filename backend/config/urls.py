"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path

from accounts.views import RoleListCreateView
from common.views import api_not_found

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/roles', RoleListCreateView.as_view(), name='role-list'),
    path('api/', include('members.urls')),
    path('api/', include('events.urls')),
    path('api/', include('shop.urls')),
    path('api/', include('comms.urls')),
    path('api/', include('finance.urls')),
    path('api/', include('volunteering.urls')),
    path('api/', include('insights.urls')),
    # Must stay last: anything under /api/ not matched above is a JSON 404.
    re_path(r'^api/', api_not_found),
]

if settings.DEBUG:
    # Development only: lets the browser open uploaded receipts. In
    # production the web server (or object storage) serves these.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
