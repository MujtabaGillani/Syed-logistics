from django.contrib import admin

from .models import (
    Customer, GeneralVoucher, OfficeExpense, Payment,
    Item, SaleOrder, SaleOrderItem,
    Shipment, ShipmentItem, ShipmentImage, Employee,
    CompanyProfile, Invoice, InvoiceItem, SalarySlip, SalarySlipLine,
)


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('name', 'designation', 'phone_number', 'cnic', 'salary',
                    'is_active')
    list_filter = ('is_active', 'designation')
    search_fields = ('name', 'cnic', 'phone_number', 'designation')
    list_per_page = 25


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'sur_name', 'cnic', 'contact_number', 'city',
                    'customer_category', 'created_at')
    list_filter = ('customer_category', 'city', 'created_at')
    search_fields = ('name', 'sur_name', 'cnic', 'contact_number', 'email')
    list_per_page = 25


@admin.register(GeneralVoucher)
class GeneralVoucherAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'invoice_date', 'customer', 'amount',
                    'payment_type', 'is_paid', 'due_date')
    list_filter = ('payment_type', 'is_paid', 'invoice_date')
    search_fields = ('invoice_number', 'customer__name', 'customer__sur_name')
    autocomplete_fields = ('customer',)
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        # Vouchers are an audit trail - block deletion in the admin too.
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('voucher', 'amount', 'date', 'method', 'reference',
                    'created_at')
    list_filter = ('method', 'date')
    search_fields = ('voucher__invoice_number', 'reference')
    autocomplete_fields = ('voucher',)
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        # Payments are append-only ledger entries - never delete.
        return False

    def has_change_permission(self, request, obj=None):
        # ...and never edit once recorded.
        return obj is None


@admin.register(OfficeExpense)
class OfficeExpenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'expense_type', 'date', 'time')
    list_filter = ('expense_type', 'date')
    search_fields = ('name',)
    list_per_page = 25


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ('sku', 'name', 'weight_kg', 'amount', 'quantity',
                    'is_active')
    list_filter = ('is_active',)
    search_fields = ('sku', 'name')
    list_per_page = 25


class SaleOrderItemInline(admin.TabularInline):
    model = SaleOrderItem
    extra = 0


@admin.register(SaleOrder)
class SaleOrderAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'order_date', 'customer',
                    'shipment_number', 'total_amount')
    list_filter = ('order_date',)
    search_fields = ('invoice_number', 'shipment_number',
                     'customer__name', 'customer__sur_name')
    autocomplete_fields = ('customer',)
    inlines = [SaleOrderItemInline]
    list_per_page = 25

    def has_delete_permission(self, request, obj=None):
        # Sale orders are ledger debits - preserve the audit trail.
        return False


class ShipmentItemInline(admin.TabularInline):
    model = ShipmentItem
    extra = 0


class ShipmentImageInline(admin.TabularInline):
    model = ShipmentImage
    extra = 0


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ('shipment_id', 'shipment_date', 'status')
    list_filter = ('status', 'shipment_date')
    search_fields = ('shipment_id', 'customers__name', 'customers__sur_name')
    filter_horizontal = ('customers',)
    inlines = [ShipmentItemInline, ShipmentImageInline]
    list_per_page = 25


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'invoice_date', 'bill_to_name',
                    'total_amount', 'advance_amount', 'balance_due',
                    'balance_due_date')
    list_filter = ('invoice_date', 'transport_mode', 'payment_method')
    search_fields = ('invoice_number', 'bill_to_name', 'bill_to_phone',
                     'tracking_number')
    readonly_fields = ('share_token', 'subtotal', 'tax_amount',
                       'total_amount', 'balance_due')
    inlines = [InvoiceItemInline]
    list_per_page = 25


class SalarySlipLineInline(admin.TabularInline):
    model = SalarySlipLine
    extra = 0


@admin.register(SalarySlip)
class SalarySlipAdmin(admin.ModelAdmin):
    list_display = ('slip_number', 'employee_name', 'pay_period_start',
                    'pay_period_end', 'net_pay', 'payment_status',
                    'payment_method')
    list_filter = ('payment_status', 'payment_method', 'pay_period_start')
    search_fields = ('slip_number', 'employee_name', 'cnic')
    readonly_fields = ('share_token', 'gross_earnings', 'total_deductions',
                       'net_pay')
    inlines = [SalarySlipLineInline]
    list_per_page = 25


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'is_default')
    search_fields = ('name',)

    def has_delete_permission(self, request, obj=None):
        # The default company must stay (documents fall back to it).
        return obj is None or not obj.is_default
