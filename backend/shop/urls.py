from django.urls import path

from . import razorpay_views, views

# Mounted at /api/.
urlpatterns = [
    path('products', views.ProductListCreateView.as_view(), name='product-list'),
    path('products/<int:pk>', views.ProductDetailView.as_view(), name='product-detail'),
    path('products/<int:pk>/restock', views.RestockView.as_view(), name='product-restock'),
    path('orders', views.OrderCreateView.as_view(), name='order-create'),
    path('orders/me', views.MyOrdersView.as_view(), name='order-me'),
    path('payments/config', razorpay_views.PaymentConfigView.as_view(), name='payment-config'),
    path('payments/razorpay/order', razorpay_views.RazorpayOrderView.as_view(), name='razorpay-order'),
    path('payments/razorpay/verify', razorpay_views.RazorpayVerifyView.as_view(), name='razorpay-verify'),
    path('payments/razorpay/cancel', razorpay_views.RazorpayCancelView.as_view(), name='razorpay-cancel'),
]
