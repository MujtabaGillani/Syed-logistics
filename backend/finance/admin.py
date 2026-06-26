from django.contrib import admin

from .models import Customer, GeneralVoucher, OfficeExpense


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
        # Vouchers are an audit trail — block deletion in the admin too.
        return False


@admin.register(OfficeExpense)
class OfficeExpenseAdmin(admin.ModelAdmin):
    list_display = ('name', 'amount', 'expense_type', 'date', 'time')
    list_filter = ('expense_type', 'date')
    search_fields = ('name',)
    list_per_page = 25
