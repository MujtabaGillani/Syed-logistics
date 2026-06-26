"""Finance domain models: customers, sales vouchers and office expenses.

Money is stored as ``DecimalField`` (never float) so that the figures the
finance/QA team reconcile are exact to the paisa. Vouchers are intentionally
*append/edit only* — there is no model-level delete path exposed through the
API, which keeps an auditable trail of every invoice raised.
"""
import random
import string
from decimal import Decimal

from django.db import models


def generate_invoice_number():
    """Random invoice number in the form ``AYUI-78402410`` — four uppercase
    letters, a hyphen, then eight digits."""
    letters = ''.join(random.choices(string.ascii_uppercase, k=4))
    digits = ''.join(random.choices(string.digits, k=8))
    return f'{letters}-{digits}'


def generate_shipment_id():
    """Random shipment id like ``SHP-10482755``."""
    return 'SHP-' + ''.join(random.choices(string.digits, k=8))


class Customer(models.Model):
    CATEGORY_RETAIL = 'retail'
    CATEGORY_WHOLESALE = 'wholesale'
    CATEGORY_OTHER = 'other'
    CATEGORY_CHOICES = [
        (CATEGORY_RETAIL, 'Retail'),
        (CATEGORY_WHOLESALE, 'Wholesale'),
        (CATEGORY_OTHER, 'Other'),
    ]

    name = models.CharField(max_length=255)
    sur_name = models.CharField(max_length=255)
    cnic = models.CharField('CNIC', max_length=20)
    contact_number = models.CharField(max_length=20)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=120)
    email = models.EmailField(blank=True, null=True)
    customer_category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default=CATEGORY_RETAIL
    )
    # Free-form structured attributes (kept as JSON so the schema can grow
    # without migrations). Stored as TEXT on SQLite, real JSONB on Postgres.
    meta_data = models.JSONField(blank=True, null=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.name} {self.sur_name}'.strip()

    @property
    def full_name(self):
        return f'{self.name} {self.sur_name}'.strip()


class GeneralVoucher(models.Model):
    """A sales invoice/voucher raised against a customer.

    ``is_paid`` drives the Due / Settled status used across the dashboard:
      * Due      -> outstanding receivable (``is_paid = False``)
      * Settled  -> payment received       (``is_paid = True``)
    """

    PAYMENT_CASH = 'cash'
    PAYMENT_CREDIT = 'credit'
    PAYMENT_DEBIT = 'debit'
    PAYMENT_OTHER = 'others'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_CREDIT, 'Credit'),
        (PAYMENT_DEBIT, 'Debit'),
        (PAYMENT_OTHER, 'Others'),
    ]
    # Payment types whose amount counts as a negative (e.g. debit/credit notes
    # that reduce receivables and revenue).
    NEGATIVE_PAYMENT_TYPES = {PAYMENT_DEBIT}

    invoice_number = models.CharField(
        max_length=100, unique=True, blank=True,
        help_text='Auto-generated (e.g. AYUI-78402410) if left blank.')
    invoice_date = models.DateField()
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='vouchers'
    )
    payment_type = models.CharField(max_length=20, choices=PAYMENT_CHOICES)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    due_date = models.DateField(blank=True, null=True)
    is_paid = models.BooleanField(
        default=False, help_text='Payment received in full.'
    )
    # When set, this voucher is a RECEIPT that knocks off (credits) the linked
    # sale order's balance instead of being a standalone invoice (debit).
    sale_order = models.ForeignKey(
        'SaleOrder', on_delete=models.PROTECT, related_name='receipts',
        null=True, blank=True,
        help_text='If set, this voucher is a receipt against that sale order.'
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_number} — {self.customer}'

    def save(self, *args, **kwargs):
        # Auto-assign a unique invoice number on first save if none was given.
        if not self.invoice_number:
            for _ in range(50):
                candidate = generate_invoice_number()
                if not GeneralVoucher.objects.filter(
                        invoice_number=candidate).exists():
                    self.invoice_number = candidate
                    break
            else:  # pragma: no cover - astronomically unlikely
                raise RuntimeError('Could not generate a unique invoice number.')
        super().save(*args, **kwargs)

    @property
    def is_receipt(self):
        """True when this voucher is a receipt against a sale order (a credit),
        rather than a standalone invoice (a debit)."""
        return self.sale_order_id is not None

    @property
    def status(self):
        return 'settled' if self.is_paid else 'due'

    @property
    def signed_amount(self):
        """Amount with its accounting sign applied. Debit vouchers are
        negative (they reduce revenue / receivables); everything else is
        positive. The stored ``amount`` itself always remains non-negative."""
        if self.payment_type in self.NEGATIVE_PAYMENT_TYPES:
            return -self.amount
        return self.amount

    @property
    def is_negative(self):
        return self.payment_type in self.NEGATIVE_PAYMENT_TYPES

    @property
    def total_paid(self):
        """Sum of payments knocked off against this voucher (uses the
        annotated value when available to avoid an extra query)."""
        annotated = getattr(self, 'paid_total', None)
        if annotated is not None:
            return annotated
        return self.payments.aggregate(t=models.Sum('amount'))['t'] \
            or Decimal('0.00')

    @property
    def outstanding(self):
        """Remaining receivable on this voucher = signed amount − payments.

        A debit/adjustment voucher carries a negative signed amount, so its
        outstanding is negative — it *reduces* the customer's balance (a credit
        note). A receipt voucher is money received against a sale order, not a
        receivable, so it contributes nothing."""
        if self.is_receipt:
            return Decimal('0.00')
        return self.signed_amount - self.total_paid

    def recompute_paid(self, save=True):
        """Refresh the derived ``is_paid`` flag from recorded payments.
        Debit/adjustment vouchers and receipt vouchers are always settled."""
        if self.is_negative or self.is_receipt:
            new_value = True
        else:
            new_value = self.outstanding <= Decimal('0.00')
        if new_value != self.is_paid:
            self.is_paid = new_value
            if save:
                super().save(update_fields=['is_paid', 'updated_at'])
        return self.is_paid


class Payment(models.Model):
    """An immutable receipt recorded against a voucher to knock off its
    balance. Payments are append-only — they can be created and read but
    never edited or deleted, preserving the ledger's integrity."""

    METHOD_CASH = 'cash'
    METHOD_CHEQUE = 'cheque'
    METHOD_BANK = 'bank'
    METHOD_ONLINE = 'online'
    METHOD_OTHER = 'other'
    METHOD_CHOICES = [
        (METHOD_CASH, 'Cash'),
        (METHOD_CHEQUE, 'Cheque'),
        (METHOD_BANK, 'Bank Transfer'),
        (METHOD_ONLINE, 'Online'),
        (METHOD_OTHER, 'Other'),
    ]

    voucher = models.ForeignKey(
        GeneralVoucher, on_delete=models.PROTECT, related_name='payments'
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    date = models.DateField()
    method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default=METHOD_CASH
    )
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['date', 'created_at']

    def __str__(self):
        return f'Payment {self.amount} on {self.voucher.invoice_number}'


class OfficeExpense(models.Model):
    TYPE_RENT = 'rent'
    TYPE_UTILITIES = 'utilities'
    TYPE_SALARY = 'salary'
    TYPE_SUPPLIES = 'supplies'
    TYPE_MAINTENANCE = 'maintenance'
    TYPE_TRAVEL = 'travel'
    TYPE_OTHER = 'other'
    TYPE_CHOICES = [
        (TYPE_RENT, 'Rent'),
        (TYPE_UTILITIES, 'Utilities'),
        (TYPE_SALARY, 'Salary'),
        (TYPE_SUPPLIES, 'Supplies'),
        (TYPE_MAINTENANCE, 'Maintenance'),
        (TYPE_TRAVEL, 'Travel'),
        (TYPE_OTHER, 'Other'),
    ]

    name = models.CharField(max_length=255)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00')
    )
    date = models.DateField()
    time = models.TimeField(blank=True, null=True)
    expense_type = models.CharField(
        max_length=30, choices=TYPE_CHOICES, default=TYPE_OTHER
    )
    image = models.ImageField(upload_to='expenses/', blank=True, null=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.name} ({self.amount})'


class Item(models.Model):
    """Catalogue of sellable items used as sale-order line defaults. Searchable
    by SKU or name (e.g. typing "LMS" lists every matching item)."""

    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=255)
    weight_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'),
        help_text='Default weight in kilograms.')
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'),
        help_text='Default charge / unit price.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.sku} — {self.name}'


class SaleOrder(models.Model):
    """A sales order / invoice for a customer, made up of line items. It posts
    a DEBIT (receivable) to the customer's ledger for ``total_amount`` and is
    knocked off by receipt vouchers (``GeneralVoucher.sale_order``).

    Like vouchers, sale orders are an audit trail: no delete, and the line
    items / total are locked once created (shipment no. & notes stay editable).
    """

    invoice_number = models.CharField(
        max_length=100, unique=True, blank=True,
        help_text='Auto-generated (e.g. AYUI-78402410) if left blank.')
    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name='sale_orders')
    shipment = models.ForeignKey(
        'Shipment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sale_orders')
    shipment_number = models.CharField(max_length=80, blank=True)
    order_date = models.DateField()
    total_amount = models.DecimalField(
        max_digits=16, decimal_places=2, default=Decimal('0.00'))
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-order_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_number} — {self.customer}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            for _ in range(50):
                candidate = generate_invoice_number()
                if not SaleOrder.objects.filter(
                        invoice_number=candidate).exists():
                    self.invoice_number = candidate
                    break
            else:  # pragma: no cover
                raise RuntimeError('Could not generate a unique invoice number.')
        super().save(*args, **kwargs)

    def recompute_total(self, save=True):
        total = self.items.aggregate(t=models.Sum('amount'))['t'] \
            or Decimal('0.00')
        if total != self.total_amount:
            self.total_amount = total
            if save:
                super().save(update_fields=['total_amount', 'updated_at'])
        return total

    @property
    def amount_received(self):
        """Total knocked off by receipt vouchers (uses an annotation when
        present to avoid an extra query)."""
        annotated = getattr(self, 'received_total', None)
        if annotated is not None:
            return annotated
        return self.receipts.aggregate(t=models.Sum('amount'))['t'] \
            or Decimal('0.00')

    @property
    def outstanding(self):
        return self.total_amount - self.amount_received

    @property
    def is_settled(self):
        return self.outstanding <= Decimal('0.00')


class SaleOrderItem(models.Model):
    """A line on a sale order. Item details are snapshotted so later catalogue
    edits never change historical orders. ``amount`` is the line charge; the
    order total is the sum of line amounts."""

    sale_order = models.ForeignKey(
        SaleOrder, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_lines')
    sku = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=255)
    weight_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'))
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.name} ({self.amount})'


class Employee(models.Model):
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    cnic = models.CharField('CNIC', max_length=20)
    designation = models.CharField(max_length=150)
    salary = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal('0.00'))
    email = models.EmailField(blank=True, null=True)
    address = models.CharField(max_length=500, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} — {self.designation}'


class Shipment(models.Model):
    """A logistics shipment. It can belong to several customers and carry many
    items and photos. Sale orders reference a shipment via ``SaleOrder.shipment``."""

    STATUS_PENDING = 'pending'
    STATUS_IN_TRANSIT = 'in_transit'
    STATUS_DELIVERED = 'delivered'
    STATUS_CANCELLED = 'cancelled'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_IN_TRANSIT, 'In Transit'),
        (STATUS_DELIVERED, 'Delivered'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    shipment_id = models.CharField(
        max_length=80, unique=True, blank=True,
        help_text='Auto-generated (e.g. SHP-10482755) if left blank.')
    customers = models.ManyToManyField(
        Customer, related_name='shipments', blank=True)
    shipment_date = models.DateField()
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-shipment_date', '-created_at']

    def __str__(self):
        return self.shipment_id

    def save(self, *args, **kwargs):
        if not self.shipment_id:
            for _ in range(50):
                candidate = generate_shipment_id()
                if not Shipment.objects.filter(shipment_id=candidate).exists():
                    self.shipment_id = candidate
                    break
            else:  # pragma: no cover
                raise RuntimeError('Could not generate a unique shipment id.')
        super().save(*args, **kwargs)

    @property
    def total_weight(self):
        total = Decimal('0.000')
        for it in self.items.all():
            total += (it.weight_kg or Decimal('0.000')) * (it.quantity or 1)
        return total


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name='items')
    item = models.ForeignKey(
        Item, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='shipment_lines')
    sku = models.CharField(max_length=80, blank=True)
    name = models.CharField(max_length=255)
    weight_kg = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal('0.000'))
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.name} x{self.quantity}'


class ShipmentImage(models.Model):
    shipment = models.ForeignKey(
        Shipment, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='shipments/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'Image #{self.pk}'
