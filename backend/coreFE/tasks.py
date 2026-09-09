from datetime import timedelta

from celery import shared_task
from django.contrib.auth.models import User
from django.utils import timezone


@shared_task
def cleanup_inactive_users():
    """Delete unapproved public signups once they are more than 48 hours old."""
    cutoff = timezone.now() - timedelta(days=2)
    stale_users = User.objects.filter(
        is_active=False,
        is_staff=False,
        is_superuser=False,
        date_joined__lt=cutoff,
        profile__isnull=False,
    )
    deleted_count, _ = stale_users.delete()
    return deleted_count
