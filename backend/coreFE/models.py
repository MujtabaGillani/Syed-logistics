from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Extra registration details for dashboard users awaiting approval."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile'
    )
    contact_number = models.CharField(max_length=30)

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.email} ({self.contact_number})'
