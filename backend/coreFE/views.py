from django.shortcuts import render
from django.views.generic import TemplateView

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

class NotFoundView(TemplateView):
    template_name = '404.html'
