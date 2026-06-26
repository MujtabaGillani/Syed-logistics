"""Finance API.

Money basis used across the dashboard
--------------------------------------
* **Revenue (accrual)** — sum of signed voucher amounts in the period
  (debit/adjustment vouchers count as negative). This is what "we billed".
* **Received** — sum of payments recorded in the period (cash actually in).
* **Outstanding (Due)** — for the invoices in the period: signed amount minus
  the payments knocked off against them (what customers still owe).
* **Expenses** — sum of office expense amounts in the period.
* **Net Profit / Loss = Revenue (accrual) − Expenses.**

Over the full (unfiltered) history these reconcile exactly:
``Received + Outstanding ≡ Revenue``.

Ledger integrity
----------------
* Vouchers cannot be deleted, and once created their money-bearing fields
  (amount, customer, invoice no./date, payment type) are locked.
* Payments are append-only (create + read only).
"""
from datetime import date
from decimal import Decimal

from django.db import models as dj_models
from django.db.models import Sum, Count, DecimalField, Value, Case, When, F
from django.db.models.functions import Coalesce, TruncMonth
from django.db.models.deletion import ProtectedError

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from . import exports, imports
from .models import (
    Customer, GeneralVoucher, OfficeExpense, Payment,
    Item, SaleOrder, Shipment, ShipmentImage, Employee,
)
from .serializers import (
    CustomerSerializer,
    GeneralVoucherSerializer,
    GeneralVoucherUpdateSerializer,
    OfficeExpenseSerializer,
    PaymentSerializer,
    ItemSerializer,
    SaleOrderSerializer,
    SaleOrderUpdateSerializer,
    ShipmentSerializer,
    EmployeeSerializer,
)

PAID_TOTAL = Coalesce(Sum('payments__amount'), Value(
    0, output_field=DecimalField(max_digits=14, decimal_places=2)))

ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))

# Signed voucher amount: debit (and any other NEGATIVE_PAYMENT_TYPES) count as
# negative so they reduce revenue / receivables; everything else is positive.
SIGNED_AMOUNT = Case(
    When(payment_type__in=GeneralVoucher.NEGATIVE_PAYMENT_TYPES,
         then=-F('amount')),
    default=F('amount'),
    output_field=DecimalField(max_digits=14, decimal_places=2),
)


def signed_total(queryset):
    """Sum of voucher amounts with the debit sign applied (never None)."""
    return queryset.aggregate(t=Coalesce(Sum(SIGNED_AMOUNT), ZERO))['t']


def _parse_date(value):
    """Parse an ISO ``YYYY-MM-DD`` string, returning ``None`` if blank/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


class CustomerViewSet(viewsets.ModelViewSet):
    """Full CRUD for customers.

    Deleting a customer that still has vouchers is blocked at the DB level
    (``on_delete=PROTECT``); we translate that into a clean 409 response.
    """

    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        search = self.request.query_params.get('search')
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(customer_category=category)
        if search:
            qs = qs.filter(
                dj_models.Q(name__icontains=search)
                | dj_models.Q(sur_name__icontains=search)
                | dj_models.Q(cnic__icontains=search)
                | dj_models.Q(contact_number__icontains=search)
                | dj_models.Q(city__icontains=search)
            )
        return qs

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return Response(
                {'detail': 'This customer has vouchers and cannot be deleted. '
                           'Remove or reassign the vouchers first.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """Customer statement: invoices as debits, payments as credits, with a
        running balance. Purely derived from immutable records — read only."""
        customer = self.get_object()
        return Response(build_customer_ledger(customer))

    @action(detail=True, methods=['get'])
    def statement(self, request, pk=None):
        """Download the customer statement as PDF or Excel (?format=pdf|excel)."""
        customer = self.get_object()
        data = build_customer_ledger(customer)
        fmt = (request.query_params.get('fmt') or 'pdf').lower()
        if fmt == 'excel':
            return exports.customer_statement_excel(customer, data)
        return exports.customer_statement_pdf(customer, data)

    @action(detail=False, methods=['get'])
    def export(self, request):
        rows = self.filter_queryset(self.get_queryset())
        fmt = (request.query_params.get('fmt') or 'excel').lower()
        if fmt == 'pdf':
            return exports.customers_pdf(rows)
        return exports.customers_excel(rows)

    @action(detail=False, methods=['post'],
            parser_classes=[MultiPartParser, FormParser])
    def import_data(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = imports.import_customers(upload)
        return Response(result, status=status.HTTP_200_OK)


class GeneralVoucherViewSet(viewsets.ModelViewSet):
    """Sales vouchers — create / read / update only.

    Vouchers are an audit trail, so DELETE is intentionally disabled.
    Supports filtering: ?from=YYYY-MM-DD&to=YYYY-MM-DD&status=due|settled|all
    &customer=<id>&search=<text>
    """

    queryset = GeneralVoucher.objects.select_related('customer').all()
    serializer_class = GeneralVoucherSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return GeneralVoucherUpdateSerializer
        return GeneralVoucherSerializer

    def get_queryset(self):
        # Annotate each voucher with the total knocked off so outstanding /
        # total_paid serialize without an extra query per row.
        qs = super().get_queryset().annotate(paid_total=PAID_TOTAL)
        params = self.request.query_params
        date_from = _parse_date(params.get('from'))
        date_to = _parse_date(params.get('to'))
        if date_from:
            qs = qs.filter(invoice_date__gte=date_from)
        if date_to:
            qs = qs.filter(invoice_date__lte=date_to)

        status_filter = (params.get('status') or 'all').lower()
        if status_filter == 'due':
            qs = qs.filter(is_paid=False)
        elif status_filter in ('settled', 'not_due', 'paid'):
            qs = qs.filter(is_paid=True)

        customer = params.get('customer')
        if customer:
            qs = qs.filter(customer_id=customer)

        sale_order = params.get('sale_order')
        if sale_order:
            qs = qs.filter(sale_order_id=sale_order)

        payment_type = params.get('payment_type')
        if payment_type:
            qs = qs.filter(payment_type=payment_type)

        search = params.get('search')
        if search:
            qs = qs.filter(
                dj_models.Q(invoice_number__icontains=search)
                | dj_models.Q(customer__name__icontains=search)
                | dj_models.Q(customer__sur_name__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        voucher = serializer.save()
        # Debit/adjustment vouchers are settled on creation.
        voucher.recompute_paid()

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        """All payments knocked off against this voucher."""
        voucher = self.get_object()
        ser = PaymentSerializer(voucher.payments.all(), many=True)
        return Response(ser.data)

    @action(detail=True, methods=['get'])
    def invoice(self, request, pk=None):
        """Download this single voucher as an invoice (?fmt=pdf|excel)."""
        voucher = self.get_object()
        fmt = (request.query_params.get('fmt') or 'pdf').lower()
        if fmt == 'excel':
            return exports.voucher_invoice_excel(voucher)
        return exports.voucher_invoice_pdf(voucher)

    @action(detail=False, methods=['get'])
    def export(self, request):
        rows = self.filter_queryset(self.get_queryset())
        fmt = (request.query_params.get('fmt') or 'excel').lower()
        if fmt == 'pdf':
            return exports.vouchers_pdf(rows)
        return exports.vouchers_excel(rows)

    @action(detail=False, methods=['post'],
            parser_classes=[MultiPartParser, FormParser])
    def import_data(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = imports.import_vouchers(upload)
        return Response(result, status=status.HTTP_200_OK)


class OfficeExpenseViewSet(viewsets.ModelViewSet):
    """Full CRUD for office expenses (supports image upload via multipart)."""

    queryset = OfficeExpense.objects.all()
    serializer_class = OfficeExpenseSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        date_from = _parse_date(params.get('from'))
        date_to = _parse_date(params.get('to'))
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        expense_type = params.get('type')
        if expense_type:
            qs = qs.filter(expense_type=expense_type)
        search = params.get('search')
        if search:
            qs = qs.filter(name__icontains=search)
        return qs

    @action(detail=False, methods=['get'])
    def export(self, request):
        rows = self.filter_queryset(self.get_queryset())
        fmt = (request.query_params.get('fmt') or 'excel').lower()
        if fmt == 'pdf':
            return exports.expenses_pdf(rows)
        return exports.expenses_excel(rows)

    @action(detail=False, methods=['post'],
            parser_classes=[MultiPartParser, FormParser])
    def import_data(self, request):
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': 'No file uploaded.'},
                            status=status.HTTP_400_BAD_REQUEST)
        result = imports.import_expenses(upload)
        return Response(result, status=status.HTTP_200_OK)


class ItemViewSet(viewsets.ModelViewSet):
    """Catalogue of items. ?search=LMS matches SKU or name (for the sale-order
    item dropdown / typeahead)."""

    queryset = Item.objects.all()
    serializer_class = ItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('active') == '1':
            qs = qs.filter(is_active=True)
        search = params.get('search')
        if search:
            qs = qs.filter(
                dj_models.Q(sku__icontains=search)
                | dj_models.Q(name__icontains=search))
        return qs


class SaleOrderViewSet(viewsets.ModelViewSet):
    """Sale orders (itemised invoices). Audit trail: no delete, and the line
    items / total / customer are locked after creation."""

    queryset = SaleOrder.objects.select_related('customer')\
        .prefetch_related('items').all()
    serializer_class = SaleOrderSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_serializer_class(self):
        if self.action in ('update', 'partial_update'):
            return SaleOrderUpdateSerializer
        return SaleOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset().annotate(received_total=Coalesce(
            Sum('receipts__amount'), Value(
                0, output_field=DecimalField(max_digits=16, decimal_places=2))))
        params = self.request.query_params
        date_from = _parse_date(params.get('from'))
        date_to = _parse_date(params.get('to'))
        if date_from:
            qs = qs.filter(order_date__gte=date_from)
        if date_to:
            qs = qs.filter(order_date__lte=date_to)
        customer = params.get('customer')
        if customer:
            qs = qs.filter(customer_id=customer)
        status_filter = (params.get('status') or 'all').lower()
        if status_filter in ('due', 'open'):
            qs = [o for o in qs if not o.is_settled]  # noqa - small sets
        elif status_filter == 'settled':
            qs = [o for o in qs if o.is_settled]
        search = params.get('search')
        if search and not isinstance(qs, list):
            qs = qs.filter(
                dj_models.Q(invoice_number__icontains=search)
                | dj_models.Q(shipment_number__icontains=search)
                | dj_models.Q(customer__name__icontains=search)
                | dj_models.Q(customer__sur_name__icontains=search))
        return qs

    @action(detail=False, methods=['get'])
    def open(self, request):
        """Sale orders with an outstanding balance — for the voucher receipt
        dropdown. Optional ?customer=<id>."""
        qs = self.get_queryset()
        if isinstance(qs, list):
            orders = qs
        else:
            orders = list(qs)
        orders = [o for o in orders if not o.is_settled]
        data = [{
            'id': o.id,
            'invoice_number': o.invoice_number,
            'customer': o.customer_id,
            'customer_name': o.customer.full_name,
            'total_amount': str(o.total_amount),
            'outstanding': str(o.outstanding),
        } for o in orders]
        return Response(data)


class EmployeeViewSet(viewsets.ModelViewSet):
    """Full CRUD for employees. ?search= matches name/cnic/phone/designation;
    ?active=1 limits to active staff."""

    queryset = Employee.objects.all()
    serializer_class = EmployeeSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if params.get('active') == '1':
            qs = qs.filter(is_active=True)
        search = params.get('search')
        if search:
            qs = qs.filter(
                dj_models.Q(name__icontains=search)
                | dj_models.Q(cnic__icontains=search)
                | dj_models.Q(phone_number__icontains=search)
                | dj_models.Q(designation__icontains=search))
        return qs


class ShipmentViewSet(viewsets.ModelViewSet):
    """Shipments with multiple customers, items and photos.

    Core fields are JSON; images are uploaded via the ``upload_images`` action
    (multipart, multiple files) and removed via ``remove_image``.
    Filter with ?customer=<id>&status=<s>&search=<text>.
    """

    queryset = Shipment.objects.prefetch_related(
        'customers', 'items', 'images').all()
    serializer_class = ShipmentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        customer = params.get('customer')
        if customer:
            qs = qs.filter(customers__id=customer)
        status_f = params.get('status')
        if status_f:
            qs = qs.filter(status=status_f)
        date_from = _parse_date(params.get('from'))
        date_to = _parse_date(params.get('to'))
        if date_from:
            qs = qs.filter(shipment_date__gte=date_from)
        if date_to:
            qs = qs.filter(shipment_date__lte=date_to)
        search = params.get('search')
        if search:
            qs = qs.filter(
                dj_models.Q(shipment_id__icontains=search)
                | dj_models.Q(customers__name__icontains=search)
                | dj_models.Q(customers__sur_name__icontains=search))
        return qs.distinct()

    @action(detail=False, methods=['get'])
    def options_list(self, request):
        """Lightweight list (id + shipment_id) for the sale-order dropdown."""
        data = [{'id': s.id, 'shipment_id': s.shipment_id}
                for s in Shipment.objects.all()]
        return Response(data)

    @action(detail=True, methods=['post'],
            parser_classes=[MultiPartParser, FormParser])
    def upload_images(self, request, pk=None):
        shipment = self.get_object()
        files = request.FILES.getlist('images') or request.FILES.getlist('image')
        if not files:
            return Response({'detail': 'No image files provided.'},
                            status=status.HTTP_400_BAD_REQUEST)
        for f in files:
            ShipmentImage.objects.create(shipment=shipment, image=f)
        # Re-fetch so the (prefetched) images relation isn't stale.
        fresh = Shipment.objects.prefetch_related(
            'customers', 'items', 'images').get(pk=shipment.pk)
        return Response(
            ShipmentSerializer(fresh, context={'request': request}).data,
            status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['delete'],
            url_path='images/(?P<img_id>[0-9]+)')
    def remove_image(self, request, pk=None, img_id=None):
        shipment = self.get_object()
        deleted, _ = shipment.images.filter(id=img_id).delete()
        if not deleted:
            return Response({'detail': 'Image not found.'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PaymentViewSet(viewsets.ModelViewSet):
    """Payments knocked off against vouchers. Append-only: create + read only,
    never edited or deleted, so the ledger stays tamper-proof.

    Filter with ?voucher=<id> or ?customer=<id>.
    """

    queryset = Payment.objects.select_related(
        'voucher', 'voucher__customer').all()
    serializer_class = PaymentSerializer
    http_method_names = ['get', 'post', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        voucher = self.request.query_params.get('voucher')
        customer = self.request.query_params.get('customer')
        if voucher:
            qs = qs.filter(voucher_id=voucher)
        if customer:
            qs = qs.filter(voucher__customer_id=customer)
        return qs

    def perform_create(self, serializer):
        payment = serializer.save()
        # Refresh the parent voucher's settled flag after knocking off.
        payment.voucher.recompute_paid()


def build_customer_ledger(customer):
    """Build a chronological customer statement (debit = invoices,
    credit = payments) with a running balance. Positive balance = the
    customer owes us."""
    lines = []

    # Sale orders — debit (customer owes the order total).
    for so in customer.sale_orders.all():
        lines.append({
            'date': so.order_date,
            'kind': 'invoice',
            'reference': so.invoice_number,
            'description': 'Sale Order'
                           + (f' — shipment {so.shipment_number}'
                              if so.shipment_number else ''),
            'debit': so.total_amount,
            'credit': None,
        })

    # General vouchers.
    for v in customer.vouchers.select_related('sale_order').all():
        if v.is_receipt:
            # Receipt against a sale order -> credit (knocks off the balance).
            lines.append({
                'date': v.invoice_date,
                'kind': 'payment',
                'reference': v.sale_order.invoice_number,
                'description': f'Receipt {v.invoice_number} '
                               f'({v.get_payment_type_display()})',
                'debit': None,
                'credit': v.amount,
            })
        else:
            # Standalone invoice -> debit (a debit-type voucher is a credit).
            lines.append({
                'date': v.invoice_date,
                'kind': 'invoice',
                'reference': v.invoice_number,
                'description': f'Voucher ({v.get_payment_type_display()})',
                'debit': v.signed_amount if v.signed_amount > 0 else None,
                'credit': -v.signed_amount if v.signed_amount < 0 else None,
            })

    # Payments knocked off standalone vouchers — credit.
    for p in Payment.objects.filter(voucher__customer=customer)\
            .select_related('voucher'):
        lines.append({
            'date': p.date,
            'kind': 'payment',
            'reference': p.voucher.invoice_number,
            'description': f'Payment received ({p.get_method_display()})'
                           + (f' — {p.reference}' if p.reference else ''),
            'debit': None,
            'credit': p.amount,
        })

    lines.sort(key=lambda x: (x['date'], 0 if x['kind'] == 'invoice' else 1))

    running = Decimal('0.00')
    total_debit = Decimal('0.00')
    total_credit = Decimal('0.00')
    for ln in lines:
        debit = ln['debit'] or Decimal('0.00')
        credit = ln['credit'] or Decimal('0.00')
        running += debit - credit
        total_debit += debit
        total_credit += credit
        ln['date'] = ln['date'].isoformat()
        ln['debit'] = str(debit) if ln['debit'] is not None else None
        ln['credit'] = str(credit) if ln['credit'] is not None else None
        ln['balance'] = str(running)

    return {
        'customer': {
            'id': customer.id,
            'name': customer.full_name,
            'cnic': customer.cnic,
            'contact_number': customer.contact_number,
            'city': customer.city,
        },
        'lines': lines,
        'totals': {
            'debit': str(total_debit),
            'credit': str(total_credit),
            'balance': str(running),
        },
    }


class DashboardSummaryView(APIView):
    """Aggregated KPIs + a 12-month profit/loss series for the dashboard.

    Optional ?from=YYYY-MM-DD&to=YYYY-MM-DD narrows the headline KPI totals
    (the trend chart always shows the trailing 12 months for context).
    """

    def get(self, request):
        date_from = _parse_date(request.query_params.get('from'))
        date_to = _parse_date(request.query_params.get('to'))

        expenses = OfficeExpense.objects.all()
        payments = Payment.objects.all()
        # Standalone vouchers (invoices/debits) vs receipt vouchers (credits).
        standalone = GeneralVoucher.objects.filter(sale_order__isnull=True)
        receipts = GeneralVoucher.objects.filter(sale_order__isnull=False)
        orders = SaleOrder.objects.all()
        if date_from:
            expenses = expenses.filter(date__gte=date_from)
            payments = payments.filter(date__gte=date_from)
            standalone = standalone.filter(invoice_date__gte=date_from)
            receipts = receipts.filter(invoice_date__gte=date_from)
            orders = orders.filter(order_date__gte=date_from)
        if date_to:
            expenses = expenses.filter(date__lte=date_to)
            payments = payments.filter(date__lte=date_to)
            standalone = standalone.filter(invoice_date__lte=date_to)
            receipts = receipts.filter(invoice_date__lte=date_to)
            orders = orders.filter(order_date__lte=date_to)

        # Revenue (accrual) = standalone voucher invoices + sale order totals.
        standalone_signed = signed_total(standalone)
        orders_total = orders.aggregate(t=Coalesce(Sum('total_amount'), ZERO))['t']
        revenue = standalone_signed + orders_total

        # Received = cash collected in the period:
        #   payments (against standalone vouchers) + receipt vouchers.
        payments_total = payments.aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        receipts_total = receipts.aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        received = payments_total + receipts_total

        # Outstanding = current open balance of the period's documents.
        paid_on_standalone = Payment.objects.filter(voucher__in=standalone)\
            .aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        received_on_orders = GeneralVoucher.objects.filter(sale_order__in=orders)\
            .aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        outstanding = (standalone_signed - paid_on_standalone) \
            + (orders_total - received_on_orders)

        total_expenses = expenses.aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        net_profit = revenue - total_expenses

        open_orders = sum(1 for o in orders if not o.is_settled)
        totals = {
            'revenue': str(revenue),
            'received': str(received),
            'outstanding': str(outstanding),
            'expenses': str(total_expenses),
            'net_profit': str(net_profit),
            'is_profit': net_profit >= 0,
            'voucher_count': standalone.count(),
            'order_count': orders.count(),
            'expense_count': expenses.count(),
            'customer_count': Customer.objects.count(),
            'due_count': standalone.filter(is_paid=False).count() + open_orders,
        }

        # --- trailing 12-month trend (independent of the KPI date filter) ---
        # Revenue per month = standalone voucher invoices (by invoice date)
        # + sale order totals (by order date).
        rev_by_month = {}
        for row in (GeneralVoucher.objects.filter(sale_order__isnull=True)
                    .annotate(m=TruncMonth('invoice_date')).values('m')
                    .annotate(t=Coalesce(Sum(SIGNED_AMOUNT), ZERO))):
            key = row['m'].date() if hasattr(row['m'], 'date') else row['m']
            rev_by_month[key] = (rev_by_month.get(key, 0) or 0) + (row['t'] or 0)
        for row in (SaleOrder.objects
                    .annotate(m=TruncMonth('order_date')).values('m')
                    .annotate(t=Coalesce(Sum('total_amount'), ZERO))):
            key = row['m'].date() if hasattr(row['m'], 'date') else row['m']
            rev_by_month[key] = (rev_by_month.get(key, 0) or 0) + (row['t'] or 0)
        exp_by_month = {
            row['m'].date() if hasattr(row['m'], 'date') else row['m']: row['t']
            for row in OfficeExpense.objects
            .annotate(m=TruncMonth('date'))
            .values('m')
            .annotate(t=Coalesce(Sum('amount'), ZERO))
        }
        # Received per month = payments (by payment date) + receipt vouchers
        # (by invoice date) — cash actually collected.
        recv_by_month = {}
        for row in (Payment.objects
                    .annotate(m=TruncMonth('date')).values('m')
                    .annotate(t=Coalesce(Sum('amount'), ZERO))):
            key = row['m'].date() if hasattr(row['m'], 'date') else row['m']
            recv_by_month[key] = (recv_by_month.get(key, 0) or 0) + (row['t'] or 0)
        for row in (GeneralVoucher.objects.filter(sale_order__isnull=False)
                    .annotate(m=TruncMonth('invoice_date')).values('m')
                    .annotate(t=Coalesce(Sum('amount'), ZERO))):
            key = row['m'].date() if hasattr(row['m'], 'date') else row['m']
            recv_by_month[key] = (recv_by_month.get(key, 0) or 0) + (row['t'] or 0)

        today = date.today()
        months = []
        year, month = today.year, today.month
        for _ in range(12):
            months.append(date(year, month, 1))
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        months.reverse()

        series = {'labels': [], 'revenue': [], 'received': [],
                  'expenses': [], 'profit': []}
        for m in months:
            rev = rev_by_month.get(m, 0) or 0
            exp = exp_by_month.get(m, 0) or 0
            recv = recv_by_month.get(m, 0) or 0
            series['labels'].append(m.strftime('%b %Y'))
            series['revenue'].append(float(rev))
            series['received'].append(float(recv))
            series['expenses'].append(float(exp))
            series['profit'].append(float(rev) - float(exp))

        # Expense breakdown by type (for a donut on the dashboard).
        breakdown = [
            {
                'type': row['expense_type'],
                'total': str(row['t']),
            }
            for row in expenses.values('expense_type')
            .annotate(t=Coalesce(Sum('amount'), ZERO))
            .order_by('-t')
        ]

        return Response({
            'totals': totals,
            'monthly': series,
            'expense_breakdown': breakdown,
        })
