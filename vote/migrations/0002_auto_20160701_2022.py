# Rekonstruktion der zweiten Migration, in Produktion am 2016-07-01 angewendet
# (django_migrations: vote/0002_auto_20160701_2022). Fuegt num_tokens und type an vote_poll an --
# genau in dieser Reihenfolge, was die Spaltenreihenfolge der Produktionstabelle bestaetigt.
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
