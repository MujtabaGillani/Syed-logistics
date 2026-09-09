from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    extra = 0


class DashboardUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'is_active', 'date_joined')
    list_filter = ('is_active', 'is_staff', 'date_joined')


admin.site.unregister(User)
admin.site.register(User, DashboardUserAdmin)

# Register your models here.
