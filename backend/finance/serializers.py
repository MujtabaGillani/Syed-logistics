from decimal import Decimal

from django.conf import settings
from django.db import transaction
from rest_framework import serializers

from .models import (
    Customer, GeneralVoucher, OfficeExpense, Payment,
    Item, SaleOrder, SaleOrderItem,
    Shipment, ShipmentItem, ShipmentImage, Employee,
    CompanyProfile, Invoice, InvoiceItem, SalarySlip, SalarySlipLine,
    compute_invoice_totals, compute_salary_totals, _q, COMPANY_DETAIL_FIELDS,
)


class EmployeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Employee
        fields = [
            'id', 'name', 'phone_number', 'cnic', 'designation', 'salary',
            'email', 'address', 'employee_code', 'department',
            'joining_date', 'bank_name', 'bank_account_title',
            'bank_account_number', 'is_active', 'created_at', 'updated_at',
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
                  'quantity', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_label(self, obj):
        return f'{obj.sku} - {obj.name}'

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


# --------------------------------------------------------------------------
# Printable documents: company profile, invoices, salary slips
# --------------------------------------------------------------------------
MAX_LOGO_BYTES = 2 * 1024 * 1024


class CompanyProfileSerializer(serializers.ModelSerializer):
    logo_url = serializers.CharField(read_only=True)

    class Meta:
        model = CompanyProfile
        fields = ['id', *COMPANY_DETAIL_FIELDS, 'logo', 'logo_url',
                  'use_site_logo', 'is_default', 'invoice_terms',
                  'invoice_notes', 'updated_at']
        read_only_fields = ['id', 'is_default', 'updated_at']
        extra_kwargs = {'logo': {'write_only': True, 'required': False}}

    def validate_name(self, value):
        if not (value or '').strip():
            raise serializers.ValidationError('Company name is required.')
        return value.strip()

    def validate_logo(self, value):
        if value and value.size > MAX_LOGO_BYTES:
            raise serializers.ValidationError('Logo must be 2 MB or smaller.')
        return value


def apply_company(attrs, instance):
    """Resolve the issuing company and the letterhead snapshot for an invoice /
    salary slip. Details sent by the form win (they may be edited for this one
    document); otherwise the selected company's details (or the default
    company's) are copied in."""
    company_given = 'company' in attrs
    company = attrs.get('company') if company_given else \
        getattr(instance, 'company', None)
    if company is None and (instance is None or company_given):
        company = CompanyProfile.load()
    attrs['company'] = company

    details = attrs.get('company_details')
    if details is None and instance is not None and not company_given:
        return attrs  # nothing about the letterhead changed
    if not details:
        attrs['company_details'] = company.snapshot() if company else {}
        return attrs
    if not isinstance(details, dict):
        raise serializers.ValidationError(
            {'company_details': 'Must be an object.'})
    clean = {}
    for key in (*COMPANY_DETAIL_FIELDS, 'logo'):
        value = details.get(key, '')
        if value is None:
            value = ''
        if not isinstance(value, str) or len(value) > 500:
            raise serializers.ValidationError(
                {'company_details': f'Invalid value for {key}.'})
        clean[key] = value.strip()
    if not clean['name']:
        raise serializers.ValidationError(
            {'company_details': 'Company name is required.'})
    # Only our own uploaded / bundled images may be printed as the logo.
    if clean['logo'] and not clean['logo'].startswith(
            (settings.MEDIA_URL, settings.STATIC_URL)):
        raise serializers.ValidationError(
            {'company_details': 'Logo must be an uploaded company logo.'})
    attrs['company_details'] = clean
    return attrs


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = ['id', 'item', 'description', 'unit', 'weight_kg',
                  'quantity', 'rate', 'amount']
        read_only_fields = ['id', 'amount']

    def validate(self, attrs):
        if (attrs.get('quantity') or 0) < 0 or (attrs.get('rate') or 0) < 0:
            raise serializers.ValidationError(
                'Quantity and rate cannot be negative.')
        return attrs


NON_NEGATIVE_INVOICE_FIELDS = ('discount', 'other_charges', 'tax_percent',
                               'advance_amount', 'amount_received')


class InvoiceSerializer(serializers.ModelSerializer):
    """Create / edit an invoice with its lines in one request. Totals, tax and
    balance are always recomputed server-side from the lines."""

    items = InvoiceItemSerializer(many=True)
    transport_mode_display = serializers.CharField(
        source='get_transport_mode_display', read_only=True)
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True)
    amount_paid = serializers.DecimalField(
        max_digits=16, decimal_places=2, read_only=True)
    payment_status = serializers.CharField(read_only=True)
    shipment_code = serializers.CharField(
        source='shipment.shipment_id', read_only=True, default=None)
    sale_order_invoice = serializers.CharField(
        source='sale_order.invoice_number', read_only=True, default=None)

    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'share_token', 'invoice_date', 'due_date',
            'company', 'company_details',
            'reference_number',
            'customer', 'bill_to_name', 'bill_to_company', 'bill_to_phone',
            'bill_to_email', 'bill_to_cnic', 'bill_to_address',
            'ship_to_name', 'ship_to_phone', 'ship_to_address',
            'shipment', 'shipment_code', 'sale_order', 'sale_order_invoice',
            'tracking_number', 'transport_mode', 'transport_mode_display',
            'service_type', 'origin', 'destination', 'vehicle_number',
            'packages', 'total_weight_kg', 'volume_cbm', 'pickup_date',
            'delivery_date',
            'items', 'subtotal', 'discount', 'other_charges_label',
            'other_charges', 'tax_percent', 'tax_amount', 'total_amount',
            'advance_amount', 'advance_date', 'amount_received',
            'received_date', 'amount_paid', 'balance_due', 'balance_due_date',
            'payment_status', 'payment_method', 'payment_method_display',
            'payment_bank_name', 'payment_account_title',
            'payment_account_number', 'transaction_reference',
            'notes', 'terms', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'share_token', 'subtotal', 'tax_amount',
                            'total_amount', 'balance_due',
                            'created_at', 'updated_at']
        extra_kwargs = {'invoice_number': {'required': False}}

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError(
                'An invoice must have at least one line item.')
        return value

    def validate(self, attrs):
        for field in NON_NEGATIVE_INVOICE_FIELDS:
            if attrs.get(field) is not None and attrs[field] < 0:
                raise serializers.ValidationError(
                    {field: 'Cannot be negative.'})

        inst = self.instance

        def get(field):
            return attrs[field] if field in attrs else getattr(inst, field, None)

        if get('advance_amount') and not get('advance_date'):
            raise serializers.ValidationError(
                {'advance_date': 'Enter the date the advance was paid.'})

        items = attrs.get('items')
        lines = ([(i.get('quantity'), i.get('rate')) for i in items]
                 if items is not None else
                 [(i.quantity, i.rate) for i in inst.items.all()])
        totals = compute_invoice_totals(
            lines, get('discount'), get('tax_percent'), get('other_charges'),
            get('advance_amount'), get('amount_received'))
        if totals['total_amount'] < 0:
            raise serializers.ValidationError(
                'Discount cannot be more than the invoice amount.')
        if totals['balance_due'] < 0:
            raise serializers.ValidationError(
                'Advance + amount received is more than the invoice total.')
        attrs.update(totals)
        return apply_company(attrs, inst)

    def _write_items(self, invoice, items):
        invoice.items.all().delete()
        for line in items:
            line['amount'] = _q(Decimal(line.get('quantity') or 0)
                                * Decimal(line.get('rate') or 0))
            InvoiceItem.objects.create(invoice=invoice, **line)

    @transaction.atomic
    def create(self, validated_data):
        items = validated_data.pop('items')
        invoice = Invoice.objects.create(**validated_data)
        self._write_items(invoice, items)
        return invoice

    @transaction.atomic
    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            self._write_items(instance, items)
        return instance


class SalarySlipLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalarySlipLine
        fields = ['id', 'kind', 'label', 'amount']
        read_only_fields = ['id']

    def validate_amount(self, value):
        if value is None or value < 0:
            raise serializers.ValidationError('Amount cannot be negative.')
        return value


class SalarySlipSerializer(serializers.ModelSerializer):
    """Create / edit a salary slip with its earning & deduction lines. Gross,
    tax, deductions and net pay are recomputed server-side."""

    lines = SalarySlipLineSerializer(many=True, required=False)
    payment_method_display = serializers.CharField(
        source='get_payment_method_display', read_only=True)
    payment_status_display = serializers.CharField(
        source='get_payment_status_display', read_only=True)

    class Meta:
        model = SalarySlip
        fields = [
            'id', 'slip_number', 'share_token', 'company', 'company_details',
            'employee',
            'employee_name', 'employee_code', 'designation', 'department',
            'cnic', 'phone_number', 'email', 'address', 'joining_date',
            'pay_period_start', 'pay_period_end', 'pay_date',
            'working_days', 'days_present', 'leaves',
            'basic_salary', 'lines', 'tax_percent', 'tax_amount',
            'gross_earnings', 'total_deductions', 'net_pay',
            'payment_status', 'payment_status_display',
            'payment_method', 'payment_method_display',
            'bank_name', 'bank_account_title', 'bank_account_number',
            'transaction_id', 'notes', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'share_token', 'gross_earnings',
                            'total_deductions', 'net_pay',
                            'created_at', 'updated_at']
        extra_kwargs = {'slip_number': {'required': False}}

    def validate(self, attrs):
        inst = self.instance

        def get(field):
            return attrs[field] if field in attrs else getattr(inst, field, None)

        for field in ('basic_salary', 'tax_percent', 'tax_amount',
                      'working_days', 'days_present', 'leaves'):
            if attrs.get(field) is not None and attrs[field] < 0:
                raise serializers.ValidationError(
                    {field: 'Cannot be negative.'})
        if (get('tax_percent') or 0) > 100:
            raise serializers.ValidationError(
                {'tax_percent': 'Tax % cannot exceed 100.'})

        start, end = get('pay_period_start'), get('pay_period_end')
        if start and end and end < start:
            raise serializers.ValidationError(
                {'pay_period_end': 'Period end must be on or after the start.'})

        lines = attrs.get('lines')
        if lines is None:
            lines = ([{'kind': ln.kind, 'amount': ln.amount}
                      for ln in inst.lines.all()] if inst else [])
        earnings = [ln['amount'] for ln in lines
                    if ln['kind'] == SalarySlipLine.KIND_EARNING]
        deductions = [ln['amount'] for ln in lines
                      if ln['kind'] == SalarySlipLine.KIND_DEDUCTION]
        totals = compute_salary_totals(
            get('basic_salary'), earnings, deductions,
            get('tax_percent'), get('tax_amount'))
        if totals['net_pay'] < 0:
            raise serializers.ValidationError(
                'Deductions are more than the gross salary.')
        attrs.update(totals)
        return apply_company(attrs, inst)

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop('lines', [])
        slip = SalarySlip.objects.create(**validated_data)
        for line in lines:
            SalarySlipLine.objects.create(slip=slip, **line)
        return slip

    @transaction.atomic
    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if lines is not None:
            instance.lines.all().delete()
            for line in lines:
                SalarySlipLine.objects.create(slip=instance, **line)
        return instance
