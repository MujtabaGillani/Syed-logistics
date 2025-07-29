from django.db import models
from django.core.exceptions import ValidationError
# Create your models here.

class Review(models.Model):
    name = models.CharField(max_length=255)
    review = models.TextField()
    rating = models.IntegerField(help_text="Rating must be between 1 and 5 (1 being minimum and 5 being maximum)") 
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return self.name

    def clean(self):
        if self.rating < 1 or self.rating > 5:
            raise ValidationError("Rating must be between 1 and 5")