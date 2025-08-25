from django.urls import path
from .views import (
    HomeView, AboutView, ContactView, FeatureView,
    PriceView, QuoteView, ServiceView, TeamView,
    TestimonialView, SupportView, TermsView, NotFoundView,
    AirFreightView, OceanFreightView, RoadFreightView, TrainFreightView,
    CustomClearanceView, WarehouseView, LogisticSolView, SupplyChainView
)

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
    path('support/', SupportView.as_view(), name='support'),
    path('terms/', TermsView.as_view(), name='terms'),
    path('404/', NotFoundView.as_view(), name='404'),

    # Service URLs
    path('services/air-freight/', AirFreightView.as_view(), name='air_freight'),
    path('services/ocean-freight/', OceanFreightView.as_view(), name='ocean_freight'),
    path('services/road-freight/', RoadFreightView.as_view(), name='road_freight'),
    path('services/train-freight/', TrainFreightView.as_view(), name='train_freight'),
    path('services/custom-clearance/', CustomClearanceView.as_view(), name='custom_clearance'),
    path('services/warehouse/', WarehouseView.as_view(), name='warehouse'),
    path('services/logistics-solutions/', LogisticSolView.as_view(), name='logistics_solutions'),
    path('services/supply-chain/', SupplyChainView.as_view(), name='supply_chain'),
]
