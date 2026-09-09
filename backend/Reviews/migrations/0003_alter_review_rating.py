from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("Reviews", "0002_alter_review_rating"),
    ]

    operations = [
        migrations.AlterField(
            model_name="review",
            name="rating",
            field=models.FloatField(
                help_text="Rating must be a number between 1 and 5 (for example, 4.5).",
                validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
            ),
        ),
    ]
