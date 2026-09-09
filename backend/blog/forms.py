import os
import tempfile

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError

from .models import BlogImage, BlogPost


def validate_media_storage():
    """Turn deployment/storage failures into an actionable form error."""
    media_root = os.fspath(settings.MEDIA_ROOT)
    try:
        os.makedirs(media_root, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=media_root):
            pass
    except OSError as exc:
        raise ValidationError(
            'The image could not be uploaded because media storage is not writable. '
            'Please contact the administrator and ask them to check the media volume permissions.'
        ) from exc


class BlogPostAdminForm(forms.ModelForm):
    class Meta:
        model = BlogPost
        fields = '__all__'

    def clean_main_image(self):
        image = self.cleaned_data.get('main_image')
        if image and getattr(image, '_committed', False) is False:
            validate_media_storage()
        return image


class BlogImageAdminForm(forms.ModelForm):
    class Meta:
        model = BlogImage
        fields = '__all__'

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and getattr(image, '_committed', False) is False:
            validate_media_storage()
        return image
