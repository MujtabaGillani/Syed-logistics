from rest_framework import serializers

from .models import Customer, GeneralVoucher, OfficeExpense


class CustomerSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    customer_category_display = serializers.CharField(
        source='get_customer_category_display', read_only=True
    )
    voucher_count = serializers.IntegerField(
        source='vouchers.count', read_only=True
    )

    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'sur_name', 'full_name', 'cnic', 'contact_number',
            'address', 'city', 'email', 'customer_category',
            'customer_category_display', 'meta_data', 'voucher_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_meta_data(self, value):
        # Allow null/blank but if provided it must be a JSON object.
        if value in (None, ''):
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError('meta_data must be a JSON object.')
        return value


class GeneralVoucherSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source='customer.full_name', read_only=True
    )
    payment_type_display = serializers.CharField(
        source='get_payment_type_display', read_only=True
    )
    status = serializers.CharField(read_only=True)

    class Meta:
        model = GeneralVoucher
        fields = [
            'id', 'invoice_number', 'invoice_date', 'customer', 'customer_name',
            'payment_type', 'payment_type_display', 'amount', 'due_date',
            'is_paid', 'status', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Amount cannot be negative.')
        return value


class OfficeExpenseSerializer(serializers.ModelSerializer):
    expense_type_display = serializers.CharField(
        source='get_expense_type_display', read_only=True
    )

    class Meta:
        model = OfficeExpense
        fields = [
            'id', 'name', 'amount', 'date', 'time', 'expense_type',
            'expense_type_display', 'image', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Amount cannot be negative.')
        return value
