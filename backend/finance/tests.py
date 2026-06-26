"""End-to-end API tests for the finance module.

Focus: the profit/loss arithmetic (accrual revenue, cash received, outstanding
dues, net profit) and the audit-trail rules (vouchers cannot be deleted;
customers with vouchers are protected).
"""
from decimal import Decimal

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Customer, GeneralVoucher, OfficeExpense


class FinanceApiTests(APITestCase):
    def setUp(self):
        self.customer = Customer.objects.create(
            name='Ali', sur_name='Khan', cnic='35202-1234567-1',
            contact_number='03001234567', address='123 St', city='Lahore',
            customer_category='retail',
        )

    # ---- Customer CRUD ----
    def test_create_customer_with_meta(self):
        resp = self.client.post('/api/finance/customers/', {
            'name': 'Sara', 'sur_name': 'Ahmed', 'cnic': '35202-7654321-2',
            'contact_number': '03007654321', 'address': '9 Mall Rd',
            'city': 'Karachi', 'customer_category': 'wholesale',
            'email': 'sara@example.com', 'meta_data': {'gst': 'X-1', 'tier': 'gold'},
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['meta_data']['gst'], 'X-1')
        self.assertEqual(resp.data['full_name'], 'Sara Ahmed')

    def test_protected_customer_delete(self):
        GeneralVoucher.objects.create(
            invoice_number='INV-1', invoice_date='2026-06-01',
            customer=self.customer, payment_type='cash',
            amount=Decimal('100.00'), is_paid=True,
        )
        resp = self.client.delete(f'/api/finance/customers/{self.customer.id}/')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(Customer.objects.filter(id=self.customer.id).exists())

    # ---- Voucher rules ----
    def test_voucher_cannot_be_deleted(self):
        v = GeneralVoucher.objects.create(
            invoice_number='INV-2', invoice_date='2026-06-02',
            customer=self.customer, payment_type='credit',
            amount=Decimal('500.00'), is_paid=False,
        )
        resp = self.client.delete(f'/api/finance/vouchers/{v.id}/')
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertTrue(GeneralVoucher.objects.filter(id=v.id).exists())

    def test_voucher_can_be_edited(self):
        v = GeneralVoucher.objects.create(
            invoice_number='INV-3', invoice_date='2026-06-03',
            customer=self.customer, payment_type='credit',
            amount=Decimal('500.00'), is_paid=False,
        )
        resp = self.client.patch(f'/api/finance/vouchers/{v.id}/',
                                 {'is_paid': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        v.refresh_from_db()
        self.assertTrue(v.is_paid)

    def test_voucher_status_filter(self):
        GeneralVoucher.objects.create(
            invoice_number='P-1', invoice_date='2026-06-01',
            customer=self.customer, payment_type='cash',
            amount=Decimal('100'), is_paid=True)
        GeneralVoucher.objects.create(
            invoice_number='D-1', invoice_date='2026-06-01',
            customer=self.customer, payment_type='credit',
            amount=Decimal('200'), is_paid=False)
        due = self.client.get('/api/finance/vouchers/?status=due')
        settled = self.client.get('/api/finance/vouchers/?status=settled')
        self.assertEqual(len(due.data), 1)
        self.assertEqual(due.data[0]['invoice_number'], 'D-1')
        self.assertEqual(len(settled.data), 1)
        self.assertEqual(settled.data[0]['invoice_number'], 'P-1')

    def test_voucher_date_range_filter(self):
        GeneralVoucher.objects.create(
            invoice_number='J-1', invoice_date='2026-01-15',
            customer=self.customer, payment_type='cash', amount=Decimal('10'))
        GeneralVoucher.objects.create(
            invoice_number='M-1', invoice_date='2026-03-15',
            customer=self.customer, payment_type='cash', amount=Decimal('20'))
        resp = self.client.get(
            '/api/finance/vouchers/?from=2026-02-01&to=2026-03-31')
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['invoice_number'], 'M-1')

    # ---- The money math ----
    def test_dashboard_profit_loss_math(self):
        # Revenue: 1000 (paid) + 600 (unpaid) + 400 (paid) = 2000
        GeneralVoucher.objects.create(
            invoice_number='V-1', invoice_date='2026-06-01',
            customer=self.customer, payment_type='cash',
            amount=Decimal('1000.00'), is_paid=True)
        GeneralVoucher.objects.create(
            invoice_number='V-2', invoice_date='2026-06-05',
            customer=self.customer, payment_type='credit',
            amount=Decimal('600.00'), is_paid=False)
        GeneralVoucher.objects.create(
            invoice_number='V-3', invoice_date='2026-06-10',
            customer=self.customer, payment_type='others',
            amount=Decimal('400.00'), is_paid=True)
        # Expenses: 300 + 250 = 550
        OfficeExpense.objects.create(
            name='Rent', amount=Decimal('300.00'), date='2026-06-02',
            expense_type='rent')
        OfficeExpense.objects.create(
            name='Fuel', amount=Decimal('250.00'), date='2026-06-08',
            expense_type='travel')

        resp = self.client.get('/api/finance/dashboard-summary/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        t = resp.data['totals']
        self.assertEqual(Decimal(t['revenue']), Decimal('2000.00'))
        self.assertEqual(Decimal(t['received']), Decimal('1400.00'))   # 1000 + 400
        self.assertEqual(Decimal(t['outstanding']), Decimal('600.00'))  # unpaid V-2
        self.assertEqual(Decimal(t['expenses']), Decimal('550.00'))
        self.assertEqual(Decimal(t['net_profit']), Decimal('1450.00'))  # 2000 - 550
        self.assertTrue(t['is_profit'])
        # received + outstanding must reconcile to revenue
        self.assertEqual(Decimal(t['received']) + Decimal(t['outstanding']),
                         Decimal(t['revenue']))

    def test_dashboard_loss_case(self):
        GeneralVoucher.objects.create(
            invoice_number='L-1', invoice_date='2026-06-01',
            customer=self.customer, payment_type='cash',
            amount=Decimal('100.00'), is_paid=True)
        OfficeExpense.objects.create(
            name='Big', amount=Decimal('500.00'), date='2026-06-02',
            expense_type='other')
        resp = self.client.get('/api/finance/dashboard-summary/')
        t = resp.data['totals']
        self.assertEqual(Decimal(t['net_profit']), Decimal('-400.00'))
        self.assertFalse(t['is_profit'])

    def test_dashboard_date_filtered_totals(self):
        GeneralVoucher.objects.create(
            invoice_number='Y-1', invoice_date='2025-12-31',
            customer=self.customer, payment_type='cash',
            amount=Decimal('999.00'), is_paid=True)
        GeneralVoucher.objects.create(
            invoice_number='Y-2', invoice_date='2026-06-15',
            customer=self.customer, payment_type='cash',
            amount=Decimal('100.00'), is_paid=True)
        resp = self.client.get(
            '/api/finance/dashboard-summary/?from=2026-01-01&to=2026-12-31')
        self.assertEqual(Decimal(resp.data['totals']['revenue']), Decimal('100.00'))

    def test_negative_amount_rejected(self):
        resp = self.client.post('/api/finance/vouchers/', {
            'invoice_number': 'NEG-1', 'invoice_date': '2026-06-01',
            'customer': self.customer.id, 'payment_type': 'cash',
            'amount': '-50.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
