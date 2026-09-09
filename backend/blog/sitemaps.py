from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .views import published_posts


class BlogSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return published_posts()

    def lastmod(self, item):
        return item.updated_at


class StaticViewSitemap(Sitemap):
    priority = 0.6
    changefreq = 'monthly'

    def items(self):
        return ('home', 'about', 'service', 'contact', 'blog:list')

    def location(self, item):
        return reverse(item)
