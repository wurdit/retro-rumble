# Generated by Django 4.1.7 on 2023-03-06 23:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('leaderboard', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
    ]
