import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import UserProfile
from .tasks import cleanup_inactive_users


class DashboardAuthenticationTests(TestCase):
    def signup(self, **overrides):
        payload = {
            'name': 'Ayesha Khan',
            'email': 'Ayesha@example.com',
            'contact_number': '+92 300 1234567',
            'password': 'StrongPass!482',
            'password_confirm': 'StrongPass!482',
        }
        payload.update(overrides)
        return self.client.post(
            reverse('dashboard_signup'),
            data=json.dumps(payload),
            content_type='application/json',
        )

    def test_signup_creates_inactive_user_and_profile(self):
        response = self.signup()
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='ayesha@example.com')
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.contact_number, '+92 300 1234567')

    def test_inactive_user_cannot_login_until_admin_activation(self):
        self.signup()
        credentials = json.dumps({'email': 'ayesha@example.com', 'password': 'StrongPass!482'})
        pending = self.client.post(reverse('dashboard_login'), credentials, content_type='application/json')
        self.assertEqual(pending.status_code, 403)
        self.assertIn('awaiting', pending.json()['message'])

        user = User.objects.get(username='ayesha@example.com')
        user.is_active = True
        user.save(update_fields=['is_active'])
        approved = self.client.post(reverse('dashboard_login'), credentials, content_type='application/json')
        self.assertEqual(approved.status_code, 200)

    def test_login_explains_when_email_is_not_registered(self):
        response = self.client.post(
            reverse('dashboard_login'),
            json.dumps({'email': 'missing@example.com', 'password': 'anything'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 404)
        self.assertIn('No account was found', response.json()['message'])

    def test_regular_form_login_also_handles_unknown_email(self):
        response = self.client.post(reverse('dashboard_login'), {
            'email': 'missing@example.com',
            'password': 'anything',
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.json()['message'],
            'No account was found with this email address. Please sign up first.',
        )

    def test_dashboard_and_finance_api_require_login(self):
        page = self.client.get(reverse('dashboard'))
        api = self.client.get('/api/finance/dashboard-summary/')
        self.assertEqual(page.status_code, 302)
        self.assertEqual(api.status_code, 403)

    def test_cleanup_only_deletes_stale_inactive_signups(self):
        stale = User.objects.create_user(username='stale@example.com', is_active=False)
        UserProfile.objects.create(user=stale, contact_number='1')
        User.objects.filter(pk=stale.pk).update(date_joined=timezone.now() - timedelta(days=3))
        recent = User.objects.create_user(username='recent@example.com', is_active=False)
        UserProfile.objects.create(user=recent, contact_number='2')
        active = User.objects.create_user(username='active@example.com', is_active=True)
        UserProfile.objects.create(user=active, contact_number='3')

        cleanup_inactive_users()

        self.assertFalse(User.objects.filter(pk=stale.pk).exists())
        self.assertTrue(User.objects.filter(pk=recent.pk).exists())
        self.assertTrue(User.objects.filter(pk=active.pk).exists())

# Create your tests here.
