from django.urls import path
from .views import (
    HomeView, AboutView, ContactView, FeatureView, 
    PriceView, QuoteView, ServiceView, TeamView, 
    TestimonialView, NotFoundView
)

app_name = 'coreFE'

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('about/', AboutView.as_view(), name='about'),
    path('contact/', ContactView.as_view(), name='contact'),
    path('feature/', FeatureView.as_view(), name='feature'),
    path('price/', PriceView.as_view(), name='price'),
    path('quote/', QuoteView.as_view(), name='quote'),
    path('service/', ServiceView.as_view(), name='service'),
    path('team/', TeamView.as_view(), name='team'),
    path('testimonial/', TestimonialView.as_view(), name='testimonial'),
    path('404/', NotFoundView.as_view(), name='404'),
]
