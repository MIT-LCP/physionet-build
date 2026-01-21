from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0066_enforce_public_user_uuid_constraint'),
    ]

    operations = [
        migrations.CreateModel(
            name='KhdpAccount',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                # Primary identifier from KHDP (publicUuid)
                (
                    'public_uuid',
                    models.CharField(
                        max_length=128,
                        default='',
                        blank=True,
                        unique=True,
                        help_text='KHDP publicUuid - persistent identifier',
                    ),
                ),
                # Additional KHDP user info fields
                ('khdp_user_id', models.CharField(max_length=128)),
                ('name', models.CharField(max_length=100)),
                ('affiliation', models.CharField(max_length=250)),
                ('email', models.EmailField(max_length=255)),
                ('orcid', models.CharField(max_length=50, blank=True)),
                (
                    'physionet_id',
                    models.CharField(
                        max_length=128,
                        blank=True,
                        help_text='PhysioNet public user UUID shared with KHDP',
                    ),
                ),
                # OAuth token information
                (
                    'access_token',
                    models.CharField(
                        max_length=512,
                        default='',
                        blank=True,
                    ),
                ),
                (
                    'token_type',
                    models.CharField(
                        max_length=50,
                        default='',
                        blank=True,
                    ),
                ),
                (
                    'token_expiration',
                    models.DecimalField(
                        max_digits=50,
                        decimal_places=40,
                        default=0,
                    ),
                ),
                ('datetime_added', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='khdp',
                        to='user.User',
                    ),
                ),
            ],
        ),
    ]
