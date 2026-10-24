from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0074_add_last_activation_email_sent'),
    ]

    operations = [
        migrations.AddField(
            model_name='credentialapplication',
            name='reference_user',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='reference_responses', to='user.user',
            ),
        ),
    ]
