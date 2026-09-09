from django.contrib import admin

from .models import BlogImage, BlogPost


class BlogImageInline(admin.TabularInline):
    model = BlogImage
    extra = 1
    max_num = 5
    validate_max = True
    fields = ('image', 'alt_text', 'caption', 'order')


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'published_at', 'author', 'updated_at')
    list_filter = ('status', 'published_at', 'created_at')
    search_fields = ('title', 'summary', 'content', 'keywords')
    prepopulated_fields = {'slug': ('title',)}
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'published_at'
    inlines = (BlogImageInline,)
    fieldsets = (
        ('Article', {'fields': ('title', 'slug', 'summary', 'content', 'author')}),
        ('Images', {'fields': ('main_image', 'main_image_alt')}),
        ('SEO', {'fields': ('seo_title', 'meta_description', 'keywords')}),
        ('Publishing', {'fields': ('status', 'published_at', 'created_at', 'updated_at')}),
    )


@admin.register(BlogImage)
class BlogImageAdmin(admin.ModelAdmin):
    list_display = ('post', 'order', 'caption')
    list_filter = ('post',)
