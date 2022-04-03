from django.db import migrations, models


class Migration(migrations.Migration):
    MIGRATE_AFTER_INSTALL = True

    dependencies = [
        ('user', '0041_permissions_1'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='is_superuser',
            field=models.BooleanField(
                default=False,
                help_text='Designates that this user has all permissions without explicitly assigning them.',
                verbose_name='superuser status'
            )
        )
    ]
