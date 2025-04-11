# 0066_enforce_public_user_uuid_constraints.py

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0065_backfill_public_user_uuid"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="public_user_uuid",
            field=models.UUIDField(
                unique=True,
                default=uuid.uuid4,
                null=False,
                editable=False,
                db_index=True,
                help_text="Persistent, public identifier for user accounts.",
            ),
        ),
    ]
