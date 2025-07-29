from django.urls import path
from .views import ReviewViewSet
from rest_framework.routers import DefaultRouter



urlpatterns = [
    path('get-all-reviews', ReviewViewSet.as_view(), name='get-all-reviews'),
]