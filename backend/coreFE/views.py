import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.generic import TemplateView
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import UserProfile

# Create your views here.


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfTemplateView(TemplateView):
    """TemplateView that guarantees the ``csrftoken`` cookie is set so the
    finance management pages can send it on POST/PUT/PATCH/DELETE requests."""
    pass

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

# Finance / management dashboard pages
class SecureDashboardView(LoginRequiredMixin, CsrfTemplateView):
    login_url = '/'
    redirect_field_name = 'next'


class DashboardView(SecureDashboardView):
    template_name = 'finance/dashboard.html'

class CustomersView(SecureDashboardView):
    template_name = 'finance/customers.html'

class GeneralVouchersView(SecureDashboardView):
    template_name = 'finance/general-vouchers.html'

class OfficeExpensesView(SecureDashboardView):
    template_name = 'finance/office-expenses.html'

class SaleOrdersView(SecureDashboardView):
    template_name = 'finance/sale-orders.html'

class ItemsView(SecureDashboardView):
    template_name = 'finance/items.html'

class ShipmentsView(SecureDashboardView):
    template_name = 'finance/shipments.html'

class EmployeesView(SecureDashboardView):
    template_name = 'finance/employees.html'

# Health check view for Docker
def health_check(request):
    """Health check endpoint for Docker monitoring"""
    return JsonResponse({
        "status": "healthy",
        "service": "Syed Logistics",
        "timestamp": "2025-08-25T08:00:00Z"
    })


def _request_data(request):
    if request.content_type != 'application/json':
        return request.POST.dict()
    try:
        return json.loads(request.body or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@require_POST
def dashboard_login(request):
    data = _request_data(request)
    if data is None:
        return JsonResponse({'message': 'Invalid request.'}, status=400)

    email = User.objects.normalize_email(data.get('email', '')).lower()
    password = data.get('password', '')
    # Dashboard signups use the email address as the username, while users
    # created in Django admin may have a separate username (for example,
    # username="Shoaib" and email="sgillani58@gmail.com").  Resolve either
    # kind of account by the email entered in the login form.
    account = User.objects.filter(email__iexact=email).only('username', 'is_active').first()
    if account is None:
        account = User.objects.filter(username__iexact=email).only('username', 'is_active').first()
    if account is None:
        return JsonResponse({
            'message': 'No account was found with this email address. Please sign up first.'
        }, status=404)

    if not account.is_active:
        return JsonResponse({
            'message': 'Your account is awaiting administrator approval.'
        }, status=403)

    user = authenticate(request, username=account.username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({'message': 'Welcome back.', 'redirect': '/dashboard/'})

    return JsonResponse({'message': 'The password you entered is incorrect.'}, status=403)


@require_POST
def dashboard_signup(request):
    data = _request_data(request)
    if data is None:
        return JsonResponse({'message': 'Invalid request.'}, status=400)

    name = ' '.join(data.get('name', '').split())
    email = User.objects.normalize_email(data.get('email', '')).lower()
    contact_number = data.get('contact_number', '').strip()
    password = data.get('password', '')
    password_confirm = data.get('password_confirm', '')

    errors = {}
    if not name:
        errors['name'] = 'Please enter your name.'
    elif len(name) > User._meta.get_field('first_name').max_length:
        errors['name'] = 'Please enter a shorter name.'
    try:
        validate_email(email)
        if len(email) > User._meta.get_field('username').max_length:
            raise ValidationError('Email address is too long.')
    except ValidationError:
        errors['email'] = 'Please enter a valid email address.'
    else:
        if User.objects.filter(username=email).exists():
            errors['email'] = 'An account with this email already exists.'
    if not contact_number:
        errors['contact_number'] = 'Please enter your contact number.'
    elif len(contact_number) > UserProfile._meta.get_field('contact_number').max_length:
        errors['contact_number'] = 'Please enter a shorter contact number.'
    if password != password_confirm:
        errors['password_confirm'] = 'The passwords do not match.'
    else:
        candidate = User(username=email, email=email, first_name=name)
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            errors['password'] = ' '.join(exc.messages)

    if errors:
        return JsonResponse({'message': 'Please correct the highlighted fields.', 'errors': errors}, status=400)

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=name,
                password=password,
                is_active=False,
            )
            UserProfile.objects.create(user=user, contact_number=contact_number)
    except IntegrityError:
        return JsonResponse({'message': 'An account with this email already exists.'}, status=409)

    return JsonResponse({
        'message': (
            'Your account has been created but is inactive. '
            'Please contact the administrator for approval.'
        )
    }, status=201)


@require_POST
def dashboard_logout(request):
    logout(request)
    return redirect('home')
