import json

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .models import BlogPost


def published_posts():
    return BlogPost.objects.filter(
        status=BlogPost.Status.PUBLISHED,
        published_at__lte=timezone.now(),
    ).select_related('author')


class BlogListView(ListView):
    model = BlogPost
    template_name = 'blog/list.html'
    context_object_name = 'posts'
    paginate_by = 9

    def get_queryset(self):
        queryset = published_posts()
        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(summary__icontains=query)
                | Q(keywords__icontains=query)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '').strip()
        context['canonical_url'] = self.request.build_absolute_uri(reverse('blog:list'))
        return context


class BlogDetailView(DetailView):
    model = BlogPost
    template_name = 'blog/detail.html'
    context_object_name = 'post'

    def get_queryset(self):
        return published_posts().prefetch_related('secondary_images')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['related_posts'] = published_posts().exclude(pk=self.object.pk)[:3]
        canonical_url = self.request.build_absolute_uri(self.object.get_absolute_url())
        context['canonical_url'] = canonical_url
        author_name = 'Syed Logistic'
        if self.object.author:
            author_name = self.object.author.get_full_name() or self.object.author.username
        schema = {
            '@context': 'https://schema.org',
            '@type': 'BlogPosting',
            'headline': self.object.title,
            'description': self.object.page_description,
            'image': self.request.build_absolute_uri(self.object.main_image.url),
            'datePublished': self.object.published_at.isoformat(),
            'dateModified': self.object.updated_at.isoformat(),
            'mainEntityOfPage': canonical_url,
            'author': {
                '@type': 'Person' if self.object.author else 'Organization',
                'name': author_name,
            },
            'publisher': {'@type': 'Organization', 'name': 'Syed Logistic'},
        }
        context['article_schema'] = (
            json.dumps(schema, ensure_ascii=False)
            .replace('<', '\\u003c')
            .replace('>', '\\u003e')
            .replace('&', '\\u0026')
        )
        return context
