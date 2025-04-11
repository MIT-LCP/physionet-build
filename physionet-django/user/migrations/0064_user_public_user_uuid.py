from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0063_alter_training_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="public_user_uuid",
            field=models.UUIDField(
                null=True,
                editable=False,
                db_index=True,
                help_text="Persistent, public identifier for user accounts.",
            ),
        ),
    ]
