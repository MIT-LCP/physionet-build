from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0011_update_proxy_permissions'),
        ('user', '0040_user_registration_ip'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='associatedemail',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='cloudinformation',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='credentialapplication',
            options={'default_permissions': ('change',)},
        ),
        migrations.AlterModelOptions(
            name='credentialreview',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='legacycredential',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='orcid',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='profile',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='user',
            options={'default_permissions': ('view',)},
        ),
        migrations.AlterModelOptions(
            name='userlogin',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='codeofconduct',
            options={'default_permissions': ('add',)},
        ),
        migrations.AlterModelOptions(
            name='codeofconductsignature',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='question',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='training',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='trainingquestion',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='trainingregex',
            options={'default_permissions': ()},
        ),
        migrations.AlterModelOptions(
            name='trainingtype',
            options={'default_permissions': ()},
        ),
        migrations.AddField(
            model_name='user',
            name='groups',
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    'The groups this user belongs to. A user will '
                    'get all permissions granted to each of their groups.'
                ),
                related_name='user_set',
                related_query_name='user',
                to='auth.Group',
                verbose_name='groups'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='is_superuser',
            field=models.BooleanField(
                default=False,
                null=True,
                help_text='Designates that this user has all permissions without explicitly assigning them.',
                verbose_name='superuser status'
            ),
        ),
        migrations.AddField(
            model_name='user',
            name='user_permissions',
            field=models.ManyToManyField(
                blank=True,
                help_text='Specific permissions for this user.',
                related_name='user_set',
                related_query_name='user',
                to='auth.Permission',
                verbose_name='user permissions'
            ),
        ),
    ]
