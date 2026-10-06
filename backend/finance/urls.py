from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerViewSet,
    GeneralVoucherViewSet,
    OfficeExpenseViewSet,
    PaymentViewSet,
    ItemViewSet,
    SaleOrderViewSet,
    ShipmentViewSet,
    EmployeeViewSet,
    InvoiceViewSet,
    SalarySlipViewSet,
    CompanyProfileView,
    DashboardSummaryView,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'vouchers', GeneralVoucherViewSet, basename='voucher')
router.register(r'expenses', OfficeExpenseViewSet, basename='expense')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'items', ItemViewSet, basename='item')
router.register(r'sale-orders', SaleOrderViewSet, basename='saleorder')
router.register(r'shipments', ShipmentViewSet, basename='shipment')
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'salary-slips', SalarySlipViewSet, basename='salaryslip')

urlpatterns = [
    path('dashboard-summary/', DashboardSummaryView.as_view(),
         name='dashboard-summary'),
    path('company-profile/', CompanyProfileView.as_view(),
         name='company-profile'),
    path('', include(router.urls)),
]
