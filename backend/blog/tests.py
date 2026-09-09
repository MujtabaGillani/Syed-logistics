from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import BlogPost


class BlogViewsTests(TestCase):
    def make_post(self, **overrides):
        values = {
            'title': 'A practical freight guide',
            'summary': 'A useful summary for customers and search engines.',
            'content': 'Useful article content.',
            'keywords': 'freight, logistics',
            'main_image': 'blog/main/test.jpg',
            'main_image_alt': 'Cargo containers at a freight terminal',
            'status': BlogPost.Status.PUBLISHED,
            'published_at': timezone.now(),
        }
        values.update(overrides)
        return BlogPost.objects.create(**values)

    def test_published_post_is_listed_and_has_seo_metadata(self):
        post = self.make_post()
        listing = self.client.get(reverse('blog:list'))
        detail = self.client.get(post.get_absolute_url())
        self.assertContains(listing, post.title)
        self.assertContains(detail, '<link rel="canonical"', html=False)
        self.assertContains(detail, 'application/ld+json')
        self.assertContains(detail, post.page_description)

    def test_draft_and_future_posts_are_not_public(self):
        draft = self.make_post(title='Draft', status=BlogPost.Status.DRAFT)
        future = self.make_post(title='Future', published_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.client.get(draft.get_absolute_url()).status_code, 404)
        self.assertEqual(self.client.get(future.get_absolute_url()).status_code, 404)

    def test_sitemap_and_robots_are_available(self):
        self.make_post()
        self.assertEqual(self.client.get('/sitemap.xml').status_code, 200)
        self.assertContains(self.client.get('/robots.txt'), '/sitemap.xml')
