"""Finance domain models: customers, sales vouchers and office expenses.

Money is stored as ``DecimalField`` (never float) so that the figures the
finance/QA team reconcile are exact to the paisa. Vouchers are intentionally
*append/edit only* — there is no model-level delete path exposed through the
API, which keeps an auditable trail of every invoice raised.
"""
from decimal import Decimal

from django.db import models


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
    PAYMENT_OTHER = 'others'
    PAYMENT_CHOICES = [
        (PAYMENT_CASH, 'Cash'),
        (PAYMENT_CREDIT, 'Credit'),
        (PAYMENT_OTHER, 'Others'),
    ]

    invoice_number = models.CharField(max_length=100, unique=True)
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
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-created_at']

    def __str__(self):
        return f'{self.invoice_number} — {self.customer}'

    @property
    def status(self):
        return 'settled' if self.is_paid else 'due'


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
