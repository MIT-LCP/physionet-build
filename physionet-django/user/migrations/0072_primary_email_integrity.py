from django.db import migrations, models
from django.db.models import Q


def restore_primary_emails(apps, schema_editor):
    """
    Repair users left without a primary associated email (caused by the
    previously non-atomic primary-email swap and by purgeaccounts deleting
    unverified primary emails). Promote the associated email matching the
    user's email field; for users with a single associated email, promote
    it and realign the user's email field.
    """
    User = apps.get_model('user', 'User')

    broken = User.objects.exclude(
        associated_emails__is_primary_email=True
    ).prefetch_related('associated_emails')

    for user in broken:
        emails = list(user.associated_emails.all())
        match = [ae for ae in emails if ae.email == user.email]
        if match:
            match[0].is_primary_email = True
            match[0].save(update_fields=['is_primary_email'])
        elif len(emails) == 1:
            emails[0].is_primary_email = True
            emails[0].save(update_fields=['is_primary_email'])
            user.email = emails[0].email
            user.save(update_fields=['email'])


class Migration(migrations.Migration):

    dependencies = [
        ('user', '0071_alter_khdpaccount_access_token'),
    ]

    operations = [
        migrations.RunPython(restore_primary_emails,
                             migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='associatedemail',
            constraint=models.UniqueConstraint(
                condition=Q(is_primary_email=True),
                fields=('user',),
                name='unique_primary_email_per_user',
            ),
        ),
    ]
