from django.urls import path

from . import views

# Mounted at /api/.
urlpatterns = [
    path('products', views.ProductListCreateView.as_view(), name='product-list'),
    path('products/<int:pk>', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/restock', views.RestockView.as_view(), name='product-restock'),
    path('orders', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/me', views.MyOrdersView.as_view(), name='order-me'),
]
