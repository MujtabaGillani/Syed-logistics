from decimal import Decimal

from rest_framework import serializers

from .models import (
    Customer, GeneralVoucher, OfficeExpense, Payment,
    Item, SaleOrder, SaleOrderItem,
    Shipment, ShipmentItem, ShipmentImage, Employee,
)


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'phone_number', 'cnic', 'designation', 'salary',
            'email', 'address', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_salary(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Salary cannot be negative.')
        return value


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
    # Optional on input: for a receipt voucher the customer is taken from the
    # linked sale order (enforced in validate()).
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(), required=False)
    customer_name = serializers.CharField(
        source='customer.full_name', read_only=True
    )
    payment_type_display = serializers.CharField(
        source='get_payment_type_display', read_only=True
    )
    status = serializers.CharField(read_only=True)
    signed_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    total_paid = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    outstanding = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    is_receipt = serializers.BooleanField(read_only=True)
    sale_order_invoice = serializers.CharField(
        source='sale_order.invoice_number', read_only=True, default=None
    )

    class Meta:
        model = GeneralVoucher
        fields = [
            'id', 'invoice_number', 'invoice_date', 'customer', 'customer_name',
            'payment_type', 'payment_type_display', 'amount', 'signed_amount',
            'total_paid', 'outstanding', 'due_date', 'is_paid', 'status',
            'sale_order', 'sale_order_invoice', 'is_receipt',
            'notes', 'created_at', 'updated_at',
        ]
        # invoice_number is auto-generated; is_paid is derived from payments.
        read_only_fields = ['id', 'invoice_number', 'is_paid',
                            'created_at', 'updated_at']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Amount cannot be negative.')
        return value

    def validate(self, attrs):
        # When a voucher is a receipt against a sale order, force the customer
        # to the order's customer and cap the amount at the order's balance.
        order = attrs.get('sale_order')
        if order is not None:
            attrs['customer'] = order.customer
            amount = attrs.get('amount')
            if amount is not None and amount > order.outstanding:
                raise serializers.ValidationError(
                    f'Receipt ({amount}) exceeds the outstanding balance '
                    f'({order.outstanding}) on order {order.invoice_number}.')
        elif not attrs.get('customer') and not self.instance:
            # Standalone invoice must name a customer.
            raise serializers.ValidationError(
                {'customer': 'This field is required.'})
        return attrs


class GeneralVoucherUpdateSerializer(GeneralVoucherSerializer):
    """Used for edits. The money-bearing fields are locked once a voucher
    exists so the ledger balance can never be retroactively changed; only
    notes and the due date remain editable. Corrections are made by posting
    a new debit/credit voucher or payment, not by editing history."""

    # Re-declared read-only: an explicitly declared field on the base class
    # can't be locked via Meta.read_only_fields, so override it here.
    customer = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta(GeneralVoucherSerializer.Meta):
        read_only_fields = GeneralVoucherSerializer.Meta.read_only_fields + [
            'invoice_number', 'invoice_date', 'payment_type',
            'amount', 'sale_order',
        ]


class PaymentSerializer(serializers.ModelSerializer):
    method_display = serializers.CharField(
        source='get_method_display', read_only=True
    )
    invoice_number = serializers.CharField(
        source='voucher.invoice_number', read_only=True
    )
    customer_name = serializers.CharField(
        source='voucher.customer.full_name', read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'id', 'voucher', 'invoice_number', 'customer_name', 'amount',
            'date', 'method', 'method_display', 'reference', 'notes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_amount(self, value):
        if value is None or value <= 0:
            raise serializers.ValidationError(
                'Payment amount must be greater than zero.')
        return value

    def validate(self, attrs):
        voucher = attrs.get('voucher')
        amount = attrs.get('amount')
        if voucher is None or amount is None:
            return attrs
        if voucher.is_receipt:
            raise serializers.ValidationError(
                'This voucher is itself a receipt against a sale order; it '
                'cannot receive payments.')
        if voucher.is_negative:
            raise serializers.ValidationError(
                'Payments cannot be recorded against a debit/adjustment voucher.')
        remaining = voucher.outstanding
        if amount > remaining:
            raise serializers.ValidationError(
                f'Payment ({amount}) exceeds the outstanding balance '
                f'({remaining}) on invoice {voucher.invoice_number}.')
        return attrs


class ItemSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = Item
        fields = ['id', 'sku', 'name', 'label', 'weight_kg', 'amount',
                  'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_label(self, obj):
        return f'{obj.sku} — {obj.name}'

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Amount cannot be negative.')
        return value


class SaleOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleOrderItem
        fields = ['id', 'item', 'sku', 'name', 'weight_kg', 'amount']
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Line amount cannot be negative.')
        return value


class SaleOrderSerializer(serializers.ModelSerializer):
    items = SaleOrderItemSerializer(many=True)
    customer_name = serializers.CharField(
        source='customer.full_name', read_only=True)
    shipment_code = serializers.CharField(
        source='shipment.shipment_id', read_only=True, default=None)
    amount_received = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True)
    outstanding = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True)
    is_settled = serializers.BooleanField(read_only=True)

    class Meta:
        model = SaleOrder
        fields = [
            'id', 'invoice_number', 'customer', 'customer_name',
            'shipment', 'shipment_code', 'shipment_number', 'order_date',
            'items', 'total_amount', 'amount_received', 'outstanding',
            'is_settled', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'invoice_number', 'total_amount',
                            'created_at', 'updated_at']

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                'A sale order must have at least one item.')
        return value

    def create(self, validated_data):
        items = validated_data.pop('items')
        # Mirror the linked shipment's id into shipment_number for display.
        shipment = validated_data.get('shipment')
        if shipment and not validated_data.get('shipment_number'):
            validated_data['shipment_number'] = shipment.shipment_id
        order = SaleOrder.objects.create(**validated_data)
        for line in items:
            # Snapshot item details so later catalogue edits don't alter history.
            item = line.get('item')
            if item is not None:
                line.setdefault('sku', item.sku)
                line.setdefault('name', item.name)
            SaleOrderItem.objects.create(sale_order=order, **line)
        order.recompute_total()
        return order


class SaleOrderUpdateSerializer(SaleOrderSerializer):
    """Edits: line items, total, customer and date are locked once the order
    is posted (it is a ledger debit). Only shipment and notes change."""

    items = SaleOrderItemSerializer(many=True, read_only=True)

    class Meta(SaleOrderSerializer.Meta):
        read_only_fields = SaleOrderSerializer.Meta.read_only_fields + [
            'customer', 'order_date', 'items',
        ]


class ShipmentItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentItem
        fields = ['id', 'item', 'sku', 'name', 'weight_kg', 'quantity']
        read_only_fields = ['id']


class ShipmentImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShipmentImage
        fields = ['id', 'image', 'uploaded_at']
        read_only_fields = ['id', 'uploaded_at']


class ShipmentSerializer(serializers.ModelSerializer):
    items = ShipmentItemSerializer(many=True, required=False)
    images = ShipmentImageSerializer(many=True, read_only=True)
    customers_detail = serializers.SerializerMethodField()
    status_display = serializers.CharField(
        source='get_status_display', read_only=True)
    total_weight = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True)
    image_count = serializers.IntegerField(
        source='images.count', read_only=True)

    class Meta:
        model = Shipment
        fields = [
            'id', 'shipment_id', 'customers', 'customers_detail',
            'shipment_date', 'status', 'status_display', 'items',
            'images', 'image_count', 'total_weight', 'notes',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'shipment_id', 'created_at', 'updated_at']

    def get_customers_detail(self, obj):
        return [{'id': c.id, 'name': c.full_name} for c in obj.customers.all()]

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        customers = validated_data.pop('customers', [])
        shipment = Shipment.objects.create(**validated_data)
        if customers:
            shipment.customers.set(customers)
        for line in items:
            item = line.get('item')
            if item is not None:
                line.setdefault('sku', item.sku)
                line.setdefault('name', item.name)
            ShipmentItem.objects.create(shipment=shipment, **line)
        return shipment

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        customers = validated_data.pop('customers', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if customers is not None:
            instance.customers.set(customers)
        if items is not None:
            instance.items.all().delete()
            for line in items:
                item = line.get('item')
                if item is not None:
                    line.setdefault('sku', item.sku)
                    line.setdefault('name', item.name)
                ShipmentItem.objects.create(shipment=instance, **line)
        return instance


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
