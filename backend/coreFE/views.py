from django.shortcuts import render
from django.views.generic import TemplateView
from django.http import JsonResponse

# Create your views here.

class HomeView(TemplateView):
    template_name = 'index.html'

class AboutView(TemplateView):
    template_name = 'about.html'

class ContactView(TemplateView):
    template_name = 'contact.html'

class FeatureView(TemplateView):
    template_name = 'feature.html'

class PriceView(TemplateView):
    template_name = 'price.html'

class QuoteView(TemplateView):
    template_name = 'quote.html'

class ServiceView(TemplateView):
    template_name = 'service.html'

class TeamView(TemplateView):
    template_name = 'team.html'

class TestimonialView(TemplateView):
    template_name = 'testimonial.html'

class SupportView(TemplateView):
    template_name = 'support.html'

class TermsView(TemplateView):
    template_name = 'terms-and-conditions.html'

class NotFoundView(TemplateView):
    template_name = '404.html'

# Service Views
class AirFreightView(TemplateView):
    template_name = 'services/airfrieght.html'

class OceanFreightView(TemplateView):
    template_name = 'services/oceanFrieght.html'

class RoadFreightView(TemplateView):
    template_name = 'services/roadFrieght.html'

class TrainFreightView(TemplateView):
    template_name = 'services/trainFrieght.html'

class CustomClearanceView(TemplateView):
    template_name = 'services/customClearance.html'

class WarehouseView(TemplateView):
    template_name = 'services/warehouse.html'

class LogisticSolView(TemplateView):
    template_name = 'services/LogisticSol.html'

class SupplyChainView(TemplateView):
    template_name = 'services/Supplychain.html'

# Health check view for Docker
def health_check(request):
    """Health check endpoint for Docker monitoring"""
    return JsonResponse({
        "status": "healthy",
        "service": "Syed Logistics",
        "timestamp": "2025-08-25T08:00:00Z"
    })
