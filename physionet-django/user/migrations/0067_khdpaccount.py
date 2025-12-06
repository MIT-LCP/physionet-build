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
                ('khdp_id', models.CharField(max_length=128, unique=True)),
                ('khdp_username', models.CharField(max_length=128)),
                ('khdp_email', models.EmailField()),
                ('linked_at', models.DateTimeField(auto_now_add=True)),
                (
                    'user',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='khdp_account',
                        to='user.User',
                    ),
                ),
            ],
        ),
    ]
