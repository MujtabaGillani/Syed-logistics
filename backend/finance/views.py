"""Finance API.

Money basis used across the dashboard
--------------------------------------
* **Revenue (accrual)** — sum of *all* voucher amounts in the period, regardless
  of whether payment has been received. This is what "we billed".
* **Received** — sum of voucher amounts where ``is_paid = True`` (cash in).
* **Outstanding (Due)** — sum of voucher amounts where ``is_paid = False``.
* **Expenses** — sum of office expense amounts in the period.
* **Net Profit / Loss = Revenue (accrual) − Expenses.**

Keeping the basis explicit avoids the classic finance ambiguity where two
reports disagree because one is cash and the other accrual.
"""
from datetime import date

from django.db import models as dj_models
from django.db.models import Sum, Count, DecimalField, Value
from django.db.models.functions import Coalesce, TruncMonth
from django.db.models.deletion import ProtectedError

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from .models import Customer, GeneralVoucher, OfficeExpense
from .serializers import (
    CustomerSerializer,
    GeneralVoucherSerializer,
    OfficeExpenseSerializer,
)

ZERO = Value(0, output_field=DecimalField(max_digits=14, decimal_places=2))


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


class GeneralVoucherViewSet(viewsets.ModelViewSet):
    """Sales vouchers — create / read / update only.

    Vouchers are an audit trail, so DELETE is intentionally disabled.
    Supports filtering: ?from=YYYY-MM-DD&to=YYYY-MM-DD&status=due|settled|all
    &customer=<id>&search=<text>
    """

    queryset = GeneralVoucher.objects.select_related('customer').all()
    serializer_class = GeneralVoucherSerializer
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
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


class DashboardSummaryView(APIView):
    """Aggregated KPIs + a 12-month profit/loss series for the dashboard.

    Optional ?from=YYYY-MM-DD&to=YYYY-MM-DD narrows the headline KPI totals
    (the trend chart always shows the trailing 12 months for context).
    """

    def get(self, request):
        date_from = _parse_date(request.query_params.get('from'))
        date_to = _parse_date(request.query_params.get('to'))

        vouchers = GeneralVoucher.objects.all()
        expenses = OfficeExpense.objects.all()
        if date_from:
            vouchers = vouchers.filter(invoice_date__gte=date_from)
            expenses = expenses.filter(date__gte=date_from)
        if date_to:
            vouchers = vouchers.filter(invoice_date__lte=date_to)
            expenses = expenses.filter(date__lte=date_to)

        revenue = vouchers.aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        received = vouchers.filter(is_paid=True).aggregate(
            t=Coalesce(Sum('amount'), ZERO))['t']
        outstanding = vouchers.filter(is_paid=False).aggregate(
            t=Coalesce(Sum('amount'), ZERO))['t']
        total_expenses = expenses.aggregate(t=Coalesce(Sum('amount'), ZERO))['t']
        net_profit = revenue - total_expenses

        totals = {
            'revenue': str(revenue),
            'received': str(received),
            'outstanding': str(outstanding),
            'expenses': str(total_expenses),
            'net_profit': str(net_profit),
            'is_profit': net_profit >= 0,
            'voucher_count': vouchers.count(),
            'expense_count': expenses.count(),
            'customer_count': Customer.objects.count(),
            'due_count': vouchers.filter(is_paid=False).count(),
        }

        # --- trailing 12-month trend (independent of the KPI date filter) ---
        rev_by_month = {
            row['m'].date() if hasattr(row['m'], 'date') else row['m']: row['t']
            for row in GeneralVoucher.objects
            .annotate(m=TruncMonth('invoice_date'))
            .values('m')
            .annotate(t=Coalesce(Sum('amount'), ZERO))
        }
        exp_by_month = {
            row['m'].date() if hasattr(row['m'], 'date') else row['m']: row['t']
            for row in OfficeExpense.objects
            .annotate(m=TruncMonth('date'))
            .values('m')
            .annotate(t=Coalesce(Sum('amount'), ZERO))
        }

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

        series = {'labels': [], 'revenue': [], 'expenses': [], 'profit': []}
        for m in months:
            rev = rev_by_month.get(m, 0) or 0
            exp = exp_by_month.get(m, 0) or 0
            series['labels'].append(m.strftime('%b %Y'))
            series['revenue'].append(float(rev))
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
