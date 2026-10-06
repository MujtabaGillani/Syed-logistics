"""Finance domain models: customers, sales vouchers and office expenses.

Money is stored as ``DecimalField`` (never float) so that the figures the
finance/QA team reconcile are exact to the paisa. Vouchers are intentionally
*append/edit only* - there is no model-level delete path exposed through the
API, which keeps an auditable trail of every invoice raised.
"""
import random
import string
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models


def generate_invoice_number():
    """Random invoice number in the form ``AYUI-78402410`` - four uppercase
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
        return f'{self.invoice_number} - {self.customer}'

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
        outstanding is negative - it *reduces* the customer's balance (a credit
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
    balance. Payments are append-only - they can be created and read but
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
    quantity = models.PositiveIntegerField(
        default=1,
        help_text='Default quantity used when the item is added to a '
                  'shipment or invoice line.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.sku} - {self.name}'


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
        return f'{self.invoice_number} - {self.customer}'

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
    # Optional HR / payroll details - used to pre-fill salary slips.
    employee_code = models.CharField(max_length=50, blank=True)
    department = models.CharField(max_length=150, blank=True)
    joining_date = models.DateField(blank=True, null=True)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(
        max_length=60, blank=True, help_text='Account number or IBAN.')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} - {self.designation}'


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


# --------------------------------------------------------------------------
# Printable documents: company profile, customer invoices and salary slips.
#
# These are standalone documents (generate -> preview -> PDF / WhatsApp). They
# do NOT post to the customer ledger or the P&L, so the existing voucher /
# sale-order / expense figures on the dashboard are unaffected.
# --------------------------------------------------------------------------
TWO_PLACES = Decimal('0.01')


def _q(value):
    """Round to 2 decimal places (half-up, like a calculator)."""
    return Decimal(value or 0).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def next_document_number(model, field, prefix):
    """Next sequential number for ``prefix`` (e.g. ``INV-2026-0007``).

    Looks at the highest existing number with the same prefix, so manually
    entered numbers in another format never break the sequence."""
    last = 0
    for value in model.objects.filter(
            **{f'{field}__startswith': prefix}).values_list(field, flat=True):
        tail = value[len(prefix):]
        if tail.isdigit():
            last = max(last, int(tail))
    return f'{prefix}{last + 1:04d}'


SITE_LOGO = 'img/logo.svg'  # bundled website logo (Frontend/img/logo.svg)

COMPANY_DETAIL_FIELDS = (
    'name', 'tagline', 'address', 'phone', 'email', 'website', 'ntn', 'strn',
    'bank_name', 'bank_account_title', 'bank_account_number', 'bank_iban',
)


class CompanyProfile(models.Model):
    """A company / letterhead (name, logo, contacts, bank details) printed on
    invoices and salary slips. Several can exist (e.g. sister companies or
    branches); one is the default. Each document stores a snapshot of the
    details it was issued with (``company_details``), so editing a company
    later never alters documents already sent."""

    name = models.CharField(max_length=255, default='Syed Logistic')
    logo = models.ImageField(upload_to='companies/', blank=True, null=True)
    use_site_logo = models.BooleanField(
        default=False,
        help_text='Print the website logo when no logo has been uploaded.')
    is_default = models.BooleanField(default=False)
    tagline = models.CharField(
        max_length=255, blank=True, default='Freight & Supply Chain Solutions')
    address = models.CharField(
        max_length=500, blank=True,
        default='Ohad Center LG B-1 30 Mall Road Lahore, Punjab, Pakistan')
    phone = models.CharField(max_length=60, blank=True,
                             default='+92 329 875 6059')
    email = models.CharField(max_length=120, blank=True,
                             default='Info@syedlogistic.com')
    website = models.CharField(max_length=120, blank=True,
                               default='www.syedlogistic.com')
    ntn = models.CharField('NTN', max_length=60, blank=True)
    strn = models.CharField('STRN', max_length=60, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=60, blank=True)
    bank_iban = models.CharField('IBAN', max_length=60, blank=True)
    invoice_terms = models.TextField(
        blank=True,
        default=('1. Payment is due by the agreed date mentioned on this '
                 'invoice.\n'
                 "2. Goods are carried at owner's risk unless insured.\n"
                 '3. Claims must be reported within 7 days of delivery.'))
    invoice_notes = models.TextField(
        blank=True, default='Thank you for choosing Syed Logistic.')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_default', 'name']
        verbose_name = 'Company'
        verbose_name_plural = 'Companies'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # The first company is always the default; only one default at a time.
        if not self.is_default and not CompanyProfile.objects.exclude(
                pk=self.pk).filter(is_default=True).exists():
            self.is_default = True
        super().save(*args, **kwargs)
        if self.is_default:
            CompanyProfile.objects.exclude(pk=self.pk).filter(
                is_default=True).update(is_default=False)

    @classmethod
    def load(cls):
        """The default company (created with Syed Logistic details if none)."""
        obj = cls.objects.filter(is_default=True).first() or cls.objects.first()
        if obj is None:
            obj = cls.objects.create(is_default=True, use_site_logo=True)
        return obj

    @property
    def logo_url(self):
        if self.logo:
            return self.logo.url
        if self.use_site_logo:
            return settings.STATIC_URL + SITE_LOGO
        return ''

    def snapshot(self):
        """The details printed on a document (stored on the document)."""
        data = {f: getattr(self, f) or '' for f in COMPANY_DETAIL_FIELDS}
        data['logo'] = self.logo_url
        return data


DOC_PAYMENT_CASH = 'cash'
DOC_PAYMENT_BANK = 'bank'
DOC_PAYMENT_CHEQUE = 'cheque'
DOC_PAYMENT_ONLINE = 'online'
DOC_PAYMENT_CHOICES = [
    (DOC_PAYMENT_CASH, 'Cash'),
    (DOC_PAYMENT_BANK, 'Bank Transfer'),
    (DOC_PAYMENT_CHEQUE, 'Cheque'),
    (DOC_PAYMENT_ONLINE, 'Online (JazzCash / Easypaisa)'),
]


def compute_invoice_totals(lines, discount=0, tax_percent=0, other_charges=0,
                           advance_amount=0, amount_received=0):
    """Pure calculation used by the serializer (mirrored by the JS preview).
    ``lines`` is an iterable of ``(quantity, rate)``.

        subtotal = sum(round(qty * rate))
        taxable  = subtotal - discount + other_charges
        tax      = taxable * tax% / 100
        total    = taxable + tax
        balance  = total - advance - received
    """
    subtotal = _q(sum((_q(Decimal(qty or 0) * Decimal(rate or 0))
                       for qty, rate in lines), Decimal('0')))
    taxable = subtotal - _q(discount) + _q(other_charges)
    tax_amount = _q(taxable * Decimal(tax_percent or 0) / Decimal('100'))
    total = _q(taxable + tax_amount)
    balance = _q(total - _q(advance_amount) - _q(amount_received))
    return {
        'subtotal': subtotal,
        'tax_amount': tax_amount,
        'total_amount': total,
        'balance_due': balance,
    }


class Invoice(models.Model):
    """A customer-facing logistics invoice built in the Invoice workspace."""

    MODE_ROAD = 'road'
    MODE_AIR = 'air'
    MODE_SEA = 'sea'
    MODE_RAIL = 'rail'
    MODE_COURIER = 'courier'
    MODE_OTHER = 'other'
    MODE_CHOICES = [
        (MODE_ROAD, 'Road Freight'),
        (MODE_AIR, 'Air Freight'),
        (MODE_SEA, 'Sea Freight'),
        (MODE_RAIL, 'Rail Freight'),
        (MODE_COURIER, 'Courier'),
        (MODE_OTHER, 'Other'),
    ]

    invoice_number = models.CharField(
        max_length=60, unique=True, blank=True,
        help_text='Auto-generated (e.g. INV-2026-0001) if left blank.')
    share_token = models.UUIDField(default=uuid.uuid4, unique=True,
                                   editable=False)
    invoice_date = models.DateField()
    due_date = models.DateField(blank=True, null=True)
    reference_number = models.CharField(
        max_length=100, blank=True, help_text='PO / order / booking reference.')

    # Issuing company + the letterhead snapshot printed on this invoice.
    company = models.ForeignKey(
        CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoices')
    company_details = models.JSONField(default=dict, blank=True)

    # Customer (optional link + the snapshot printed on the invoice).
    customer = models.ForeignKey(
        Customer, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoices')
    bill_to_name = models.CharField(max_length=255)
    bill_to_company = models.CharField(max_length=255, blank=True)
    bill_to_phone = models.CharField(max_length=60, blank=True)
    bill_to_email = models.CharField(max_length=120, blank=True)
    bill_to_cnic = models.CharField('Bill-to CNIC / NTN', max_length=60,
                                    blank=True)
    bill_to_address = models.TextField(blank=True)
    ship_to_name = models.CharField(max_length=255, blank=True)
    ship_to_phone = models.CharField(max_length=60, blank=True)
    ship_to_address = models.TextField(blank=True)

    # Shipment / consignment details.
    shipment = models.ForeignKey(
        'Shipment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='invoices')
    sale_order = models.ForeignKey(
        SaleOrder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='printed_invoices')
    tracking_number = models.CharField(
        max_length=100, blank=True, help_text='Bilty / AWB / B/L / CN number.')
    transport_mode = models.CharField(max_length=20, choices=MODE_CHOICES,
                                      blank=True)
    service_type = models.CharField(
        max_length=120, blank=True, help_text='e.g. Door to door, FCL, LCL.')
    origin = models.CharField(max_length=150, blank=True)
    destination = models.CharField(max_length=150, blank=True)
    vehicle_number = models.CharField(
        max_length=100, blank=True, help_text='Vehicle / container number.')
    packages = models.PositiveIntegerField(blank=True, null=True)
    total_weight_kg = models.DecimalField(
        max_digits=12, decimal_places=3, blank=True, null=True)
    volume_cbm = models.DecimalField(
        max_digits=12, decimal_places=3, blank=True, null=True)
    pickup_date = models.DateField(blank=True, null=True)
    delivery_date = models.DateField(blank=True, null=True)

    # Money. subtotal / tax_amount / total_amount / balance_due are derived
    # from the lines and always recomputed by the serializer.
    subtotal = models.DecimalField(max_digits=16, decimal_places=2,
                                   default=Decimal('0.00'))
    discount = models.DecimalField(max_digits=16, decimal_places=2,
                                   default=Decimal('0.00'))
    other_charges_label = models.CharField(
        max_length=120, blank=True, help_text='e.g. Loading / customs / fuel.')
    other_charges = models.DecimalField(max_digits=16, decimal_places=2,
                                        default=Decimal('0.00'))
    tax_percent = models.DecimalField(max_digits=6, decimal_places=2,
                                      default=Decimal('0.00'))
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2,
                                     default=Decimal('0.00'))
    total_amount = models.DecimalField(max_digits=16, decimal_places=2,
                                       default=Decimal('0.00'))

    # Payments: the advance (with the date it was paid), any further amount
    # received (with its date) and the date agreed for the remaining balance.
    advance_amount = models.DecimalField(max_digits=16, decimal_places=2,
                                         default=Decimal('0.00'))
    advance_date = models.DateField(blank=True, null=True)
    amount_received = models.DecimalField(max_digits=16, decimal_places=2,
                                          default=Decimal('0.00'))
    received_date = models.DateField(blank=True, null=True)
    balance_due = models.DecimalField(max_digits=16, decimal_places=2,
                                      default=Decimal('0.00'))
    balance_due_date = models.DateField(
        blank=True, null=True,
        help_text='Date agreed with the customer for the remaining payment.')
    payment_method = models.CharField(max_length=20,
                                      choices=DOC_PAYMENT_CHOICES, blank=True)
    payment_bank_name = models.CharField(max_length=150, blank=True)
    payment_account_title = models.CharField(max_length=150, blank=True)
    payment_account_number = models.CharField(max_length=60, blank=True)
    transaction_reference = models.CharField(max_length=120, blank=True)

    notes = models.TextField(blank=True)
    terms = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_number} - {self.bill_to_name}'

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            year = (self.invoice_date.year if self.invoice_date
                    else date.today().year)
            self.invoice_number = next_document_number(
                Invoice, 'invoice_number', f'INV-{year}-')
        super().save(*args, **kwargs)

    @property
    def amount_paid(self):
        return _q(self.advance_amount) + _q(self.amount_received)

    @property
    def payment_status(self):
        if self.total_amount > 0 and self.balance_due <= 0:
            return 'paid'
        if self.amount_paid > 0:
            return 'partial'
        return 'unpaid'


class InvoiceItem(models.Model):
    """A charge line on an invoice (freight, loading, packing, ...)."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE,
                                related_name='items')
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True,
                             blank=True, related_name='invoice_lines')
    description = models.CharField(max_length=255)
    unit = models.CharField(max_length=30, blank=True,
                            help_text='e.g. kg, pcs, carton, trip.')
    weight_kg = models.DecimalField(max_digits=12, decimal_places=3,
                                    blank=True, null=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3,
                                   default=Decimal('1'))
    rate = models.DecimalField(max_digits=16, decimal_places=2,
                               default=Decimal('0.00'))
    amount = models.DecimalField(max_digits=16, decimal_places=2,
                                 default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.description} ({self.amount})'


def compute_salary_totals(basic_salary, earnings, deductions, tax_percent=0,
                          tax_amount=0):
    """Pure calculation used by the serializer (mirrored by the JS preview).

        gross      = basic + sum(earnings)
        tax        = gross * tax% / 100   (or the fixed tax_amount if tax% = 0)
        deductions = tax + sum(deductions)
        net        = gross - deductions
    """
    gross = _q(_q(basic_salary) + sum((_q(a) for a in earnings), Decimal('0')))
    if Decimal(tax_percent or 0) > 0:
        tax = _q(gross * Decimal(tax_percent) / Decimal('100'))
    else:
        tax = _q(tax_amount)
    total_ded = _q(tax + sum((_q(a) for a in deductions), Decimal('0')))
    return {
        'gross_earnings': gross,
        'tax_amount': tax,
        'total_deductions': total_ded,
        'net_pay': _q(gross - total_ded),
    }


class SalarySlip(models.Model):
    """A pay slip for an employee. Employee details are snapshotted so later
    HR edits never change an issued slip."""

    STATUS_PENDING = 'pending'
    STATUS_PAID = 'paid'
    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PAID, 'Paid'),
    ]

    slip_number = models.CharField(
        max_length=60, unique=True, blank=True,
        help_text='Auto-generated (e.g. SAL-2026-0001) if left blank.')
    share_token = models.UUIDField(default=uuid.uuid4, unique=True,
                                   editable=False)

    # Paying company + the letterhead snapshot printed on this slip.
    company = models.ForeignKey(
        CompanyProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_slips')
    company_details = models.JSONField(default=dict, blank=True)

    employee = models.ForeignKey(
        Employee, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='salary_slips')
    employee_name = models.CharField(max_length=255)
    employee_code = models.CharField(max_length=50, blank=True)
    designation = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=150, blank=True)
    cnic = models.CharField('CNIC', max_length=20, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    email = models.CharField(max_length=120, blank=True)
    address = models.CharField(max_length=500, blank=True)
    joining_date = models.DateField(blank=True, null=True)

    pay_period_start = models.DateField()
    pay_period_end = models.DateField()
    pay_date = models.DateField(blank=True, null=True)
    working_days = models.DecimalField(max_digits=5, decimal_places=1,
                                       blank=True, null=True)
    days_present = models.DecimalField(max_digits=5, decimal_places=1,
                                       blank=True, null=True)
    leaves = models.DecimalField(max_digits=5, decimal_places=1,
                                 blank=True, null=True)

    basic_salary = models.DecimalField(max_digits=14, decimal_places=2,
                                       default=Decimal('0.00'))
    tax_percent = models.DecimalField(
        max_digits=6, decimal_places=2, default=Decimal('0.00'),
        help_text='If set, income tax = gross x tax% (overrides tax_amount).')
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2,
                                     default=Decimal('0.00'))
    # Derived (recomputed by the serializer from basic + lines + tax).
    gross_earnings = models.DecimalField(max_digits=14, decimal_places=2,
                                         default=Decimal('0.00'))
    total_deductions = models.DecimalField(max_digits=14, decimal_places=2,
                                           default=Decimal('0.00'))
    net_pay = models.DecimalField(max_digits=14, decimal_places=2,
                                  default=Decimal('0.00'))

    payment_status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                                      default=STATUS_PAID)
    payment_method = models.CharField(max_length=20,
                                      choices=DOC_PAYMENT_CHOICES,
                                      default=DOC_PAYMENT_CASH)
    bank_name = models.CharField(max_length=150, blank=True)
    bank_account_title = models.CharField(max_length=150, blank=True)
    bank_account_number = models.CharField(max_length=60, blank=True)
    transaction_id = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-pay_period_start', '-created_at']

    def __str__(self):
        return f'{self.slip_number} - {self.employee_name}'

    def save(self, *args, **kwargs):
        if not self.slip_number:
            year = (self.pay_period_start.year if self.pay_period_start
                    else date.today().year)
            self.slip_number = next_document_number(
                SalarySlip, 'slip_number', f'SAL-{year}-')
        super().save(*args, **kwargs)


class SalarySlipLine(models.Model):
    """An allowance (earning) or deduction line on a salary slip."""

    KIND_EARNING = 'earning'
    KIND_DEDUCTION = 'deduction'
    KIND_CHOICES = [
        (KIND_EARNING, 'Earning'),
        (KIND_DEDUCTION, 'Deduction'),
    ]

    slip = models.ForeignKey(SalarySlip, on_delete=models.CASCADE,
                             related_name='lines')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    label = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=14, decimal_places=2,
                                 default=Decimal('0.00'))

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.get_kind_display()}: {self.label} ({self.amount})'
