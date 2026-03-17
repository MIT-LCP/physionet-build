from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("user", "0071_alter_khdpaccount_access_token"),
    ]

    operations = [
        migrations.CreateModel(
            name="D2eAccount",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "sub",
                    models.CharField(
                        help_text="Logto subject identifier",
                        max_length=255,
                        unique=True,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                ("email", models.EmailField(max_length=255)),
                (
                    "access_token",
                    models.CharField(blank=True, default="", max_length=2048),
                ),
                (
                    "refresh_token",
                    models.CharField(blank=True, default="", max_length=2048),
                ),
                (
                    "token_type",
                    models.CharField(blank=True, default="", max_length=50),
                ),
                (
                    "token_expiration",
                    models.DecimalField(
                        decimal_places=40, default=0, max_digits=50
                    ),
                ),
                ("datetime_added", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="d2e",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "default_permissions": (),
            },
        ),
    ]
