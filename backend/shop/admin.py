from django.contrib import admin

from common.admin import ReadOnlyAdmin, ReadOnlyInline, rupees

from .models import Order, OrderLine, ProductSize


class OrderLineInline(ReadOnlyInline):
    model = OrderLine
    fields = ['kind', 'item', 'qty', 'unit', 'line_discount', 'paid']
    readonly_fields = fields

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('plan', 'tier__event', 'product_size__product')

    @admin.display(description='Item')
    def item(self, line):
        return line.plan or line.tier or line.product_size

    @admin.display(description='Unit price')
    def unit(self, line):
        return rupees(line.unit_price)

    @admin.display(description='Discount')
    def line_discount(self, line):
        return rupees(line.discount)

    @admin.display(description='Paid')
    def paid(self, line):
        return rupees(line.amount)


@admin.register(Order)
class OrderAdmin(ReadOnlyAdmin):
    list_display = ['id', 'buyer', 'status', 'subtotal_rupees', 'discount_rupees', 'total_rupees', 'created_at']
    list_filter = ['status']
    search_fields = ['buyer__email', 'buyer__name', 'payment_ref']
    list_select_related = ['buyer']
    inlines = [OrderLineInline]

    @admin.display(description='Subtotal', ordering='subtotal')
    def subtotal_rupees(self, order):
        return rupees(order.subtotal)

    @admin.display(description='Discount', ordering='discount')
    def discount_rupees(self, order):
        return rupees(order.discount)

    @admin.display(description='Total', ordering='total')
    def total_rupees(self, order):
        return rupees(order.total)


@admin.register(ProductSize)
class ProductSizeAdmin(ReadOnlyAdmin):
    list_display = ['product', 'size', 'stock', 'price']
    list_filter = ['product']
    list_select_related = ['product']

    @admin.display(description='Base price')
    def price(self, size):
        return rupees(size.product.base_price)
