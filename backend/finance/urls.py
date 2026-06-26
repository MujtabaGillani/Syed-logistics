from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    CustomerViewSet,
    GeneralVoucherViewSet,
    OfficeExpenseViewSet,
    DashboardSummaryView,
)

router = DefaultRouter()
router.register(r'customers', CustomerViewSet, basename='customer')
router.register(r'vouchers', GeneralVoucherViewSet, basename='voucher')
router.register(r'expenses', OfficeExpenseViewSet, basename='expense')

urlpatterns = [
    path('dashboard-summary/', DashboardSummaryView.as_view(),
         name='dashboard-summary'),
    path('', include(router.urls)),
]
