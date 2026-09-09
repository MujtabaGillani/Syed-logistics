import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='BlogPost',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('slug', models.SlugField(blank=True, max_length=220, unique=True)),
                ('summary', models.CharField(help_text='A concise introduction used on cards and as the default SEO description.', max_length=320)),
                ('content', models.TextField(help_text='Main article content. Blank lines create paragraphs.')),
                ('keywords', models.CharField(blank=True, help_text='Comma-separated search phrases relevant to this article.', max_length=500)),
                ('main_image', models.ImageField(upload_to='blog/main/%Y/%m/')),
                ('main_image_alt', models.CharField(help_text='Describe the main image for accessibility and image search.', max_length=180)),
                ('seo_title', models.CharField(blank=True, help_text='Optional search-result title. The article title is used when blank.', max_length=60)),
                ('meta_description', models.CharField(blank=True, help_text='Optional search-result description. The summary is used when blank.', max_length=160)),
                ('status', models.CharField(choices=[('draft', 'Draft'), ('published', 'Published')], default='draft', max_length=10)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='blog_posts', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ('-published_at', '-created_at')},
        ),
        migrations.AddIndex(
            model_name='blogpost',
            index=models.Index(fields=['status', 'published_at'], name='blog_blogpo_status_aa5436_idx'),
        ),
        migrations.CreateModel(
            name='BlogImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='blog/secondary/%Y/%m/')),
                ('alt_text', models.CharField(max_length=180)),
                ('caption', models.CharField(blank=True, max_length=240)),
                ('order', models.PositiveSmallIntegerField(default=0)),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='secondary_images', to='blog.blogpost')),
            ],
            options={'ordering': ('order', 'id')},
        ),
    ]
