# A reconstruction of the second migration, applied in production on 2016-07-01
# (django_migrations: vote/0002_auto_20160701_2022). Appends num_tokens and type to vote_poll --
# in exactly this order, which confirms the column order of the production table.
# Details: notes/phase-2-migrations.md

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('vote', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='poll',
            name='num_tokens',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='poll',
            name='type',
            field=models.CharField(default='simple_choice', max_length=20),
        ),
    ]
