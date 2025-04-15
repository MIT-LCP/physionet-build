# 0065_backfill_public_user_uuid.py

from django.db import migrations
import uuid


def backfill_uuids(apps, schema_editor):
    User = apps.get_model("user", "User")
    for user in User.objects.filter(public_user_uuid__isnull=True):
        user.public_user_uuid = uuid.uuid4()
        user.save(update_fields=["public_user_uuid"])


class Migration(migrations.Migration):

    dependencies = [
        ("user", "0064_user_public_user_uuid"),
    ]

    operations = [
        migrations.RunPython(backfill_uuids, reverse_code=migrations.RunPython.noop),
    ]
