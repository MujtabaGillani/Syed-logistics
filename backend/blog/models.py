import math

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class BlogPost(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PUBLISHED = 'published', 'Published'

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    summary = models.CharField(
        max_length=320,
        help_text='A concise introduction used on cards and as the default SEO description.',
    )
    content = models.TextField(help_text='Main article content. Blank lines create paragraphs.')
    keywords = models.CharField(
        max_length=500,
        blank=True,
        help_text='Comma-separated search phrases relevant to this article.',
    )
    main_image = models.ImageField(upload_to='blog/main/%Y/%m/')
    main_image_alt = models.CharField(
        max_length=180,
        help_text='Describe the main image for accessibility and image search.',
    )
    seo_title = models.CharField(
        max_length=60,
        blank=True,
        help_text='Optional search-result title. The article title is used when blank.',
    )
    meta_description = models.CharField(
        max_length=160,
        blank=True,
        help_text='Optional search-result description. The summary is used when blank.',
    )
    author = models.ForeignKey(
        get_user_model(),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='blog_posts',
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-published_at', '-created_at')
        indexes = [models.Index(fields=('status', 'published_at'))]

    def __str__(self):
        return self.title

    def clean(self):
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200] or 'article'
            candidate = base
            number = 2
            while BlogPost.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f'{base[:215 - len(str(number))]}-{number}'
                number += 1
            self.slug = candidate
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blog:detail', kwargs={'slug': self.slug})

    @property
    def page_title(self):
        return self.seo_title or self.title

    @property
    def page_description(self):
        return self.meta_description or self.summary[:160]

    @property
    def reading_time(self):
        return max(1, math.ceil(len(self.content.split()) / 200))


class BlogImage(models.Model):
    post = models.ForeignKey(BlogPost, on_delete=models.CASCADE, related_name='secondary_images')
    image = models.ImageField(upload_to='blog/secondary/%Y/%m/')
    alt_text = models.CharField(max_length=180)
    caption = models.CharField(max_length=240, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ('order', 'id')

    def __str__(self):
        return f'{self.post.title} image {self.order + 1}'

    def clean(self):
        if self.post_id:
            count = BlogImage.objects.filter(post_id=self.post_id).exclude(pk=self.pk).count()
            if count >= 5:
                raise ValidationError('A blog post can have no more than five secondary images.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
