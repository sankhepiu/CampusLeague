from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import has_role

from . import stock
from .api import IdempotencyKeyReused, PaymentFailed, idempotency_key
from .models import Order, OrderLine, Product, ProductSize
from .payments import IdempotencyConflict, ProductUnavailable, merch_discount_pct, purchase_merch
from .serializers import (
    ORDER_LINE_LABEL_RELATIONS, MerchOrderSerializer, OrderSerializer, PaymentSerializer, ProductSerializer,
    ProductWriteSerializer, RestockSerializer,
)

# Plan permission table: "Manage products and stock" is P, T and EM.
ShopStaff = has_role('president', 'treasurer', 'event_manager')


class OutOfStockError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'Out of stock.'
    default_code = 'out_of_stock'


class ProductUnavailableError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = 'One of these items is no longer available.'
    default_code = 'product_unavailable'


def is_shop_staff(request):
    return ShopStaff().has_permission(request, None)


def visible_products(request):
    """ASSUMPTION: inactive products are visible to shop staff only."""
    products = Product.objects.prefetch_related('sizes')
    return products if is_shop_staff(request) else products.filter(active=True)


def price_context(request):
    user = request.user
    return {'merch_discount_pct': merch_discount_pct(user) if user.is_authenticated else 0}


class StaffWriteMixin:
    """Reads are public; writes need the shop-staff role."""

    def get_permissions(self):
        return [AllowAny()] if self.request.method == 'GET' else [ShopStaff()]

    def get_queryset(self):
        return visible_products(self.request)

    def get_serializer_context(self):
        return {**super().get_serializer_context(), **price_context(self.request)}

    def get_serializer_class(self):
        return ProductSerializer if self.request.method == 'GET' else ProductWriteSerializer


class ProductListCreateView(StaffWriteMixin, ListCreateAPIView):
    """GET /products (public), POST /products (shop staff)."""

    def create(self, request, *args, **kwargs):
        serializer = ProductWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            product = serializer.save()
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class ProductDetailView(StaffWriteMixin, RetrieveUpdateAPIView):
    """GET /products/{id} (public), PATCH /products/{id} (shop staff)."""

    http_method_names = ['get', 'patch', 'head', 'options']

    def partial_update(self, request, *args, **kwargs):
        product = self.get_object()
        serializer = ProductWriteSerializer(product, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(ProductSerializer(product).data)


class RestockView(APIView):
    """POST /products/{id}/restock. Shop staff."""

    permission_classes = [ShopStaff]

    def post(self, request, pk):
        product = get_object_or_404(Product, pk=pk)
        serializer = RestockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        size = get_object_or_404(ProductSize, product=product, size=serializer.validated_data['size'])
        stock.restock(product_size=size, quantity=serializer.validated_data['quantity'], actor=request.user)
        product = Product.objects.prefetch_related('sizes').get(pk=product.pk)
        return Response(ProductSerializer(product).data)


class OrderCreateView(APIView):
    """POST /orders. Any logged-in user. Merchandise only."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        key = idempotency_key(request)
        serializer = MerchOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            result = purchase_merch(
                # Buyer from the token; prices and discount from the server.
                user=request.user,
                items={item['product_size']: item['quantity'] for item in data['items']},
                outcome=data['test_outcome'],
                idempotency_key=key,
            )
        except stock.OutOfStock as exc:
            size = exc.product_size
            raise OutOfStockError(f'Out of stock: {size.product.name} size {size.size} has {size.stock} left.')
        except ProductUnavailable:
            raise ProductUnavailableError()
        except IdempotencyConflict:
            raise IdempotencyKeyReused()

        if result.order.status == Order.Status.CANCELLED:
            raise PaymentFailed()
        body = {
            'order': OrderSerializer(result.order).data,
            'payment': PaymentSerializer(result.payment).data if result.payment else None,
        }
        if result.order.status == Order.Status.PENDING:
            return Response(body, status=status.HTTP_202_ACCEPTED)
        return Response(body, status=status.HTTP_200_OK if result.replayed else status.HTTP_201_CREATED)


class MyOrdersView(ListAPIView):
    """GET /orders/me. Plan: "Members can read only their own ... orders"."""

    permission_classes = [IsAuthenticated]
    serializer_class = OrderSerializer

    def get_queryset(self):
        # One query for the page of orders and one for all their lines, with
        # the plan, tier, event, size and product each line's label needs
        # joined in. Without the joins every line would cost extra queries.
        lines = OrderLine.objects.select_related(*ORDER_LINE_LABEL_RELATIONS).order_by('id')
        return (
            Order.objects.filter(buyer=self.request.user)
            .prefetch_related(Prefetch('lines', queryset=lines))
            .order_by('-created_at', '-id')
        )
