from django.contrib import admin
from .models import Review
# Register your models here.

class ReviewAdmin(admin.ModelAdmin):
    list_display = ('name', 'review', 'rating', 'created_at', 'is_active')
    list_filter = ('created_at', 'is_active')
    search_fields = ('name', 'review')
    list_editable = ('is_active',)
    list_per_page = 10

admin.site.register(Review, ReviewAdmin)