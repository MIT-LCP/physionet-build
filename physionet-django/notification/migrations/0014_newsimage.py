from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notification', '0013_alter_news_guid'),
    ]

    operations = [
        migrations.CreateModel(
            name='NewsImage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filename', models.CharField(max_length=255, unique=True)),
                ('uploaded_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
    ]
