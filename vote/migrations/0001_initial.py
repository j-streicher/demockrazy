# Rekonstruktion der urspruenglichen Migration, die in Produktion am 2016-06-09 angewendet
# wurde (django_migrations: vote/0001_initial). Die Datei existierte nie im Repo, weil
# migrations/ gitignored war -- sie wurde aus dem Modellstand vor 0002 neu erzeugt und gegen
# das Schema der Produktionsdatenbank verifiziert. Name und Inhalt muessen so bleiben, damit
# `migrate` in Produktion ein No-Op ist. Details: notes/phase-2-migrations.md

import django.db.models.deletion
import django.utils.timezone
import vote.models
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Poll',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200)),
                ('question_text', models.TextField()),
                ('pub_date', models.DateTimeField(blank=True, default=django.utils.timezone.now, verbose_name='date published')),
                ('creator_token', models.CharField(default=vote.models.mk_admin_token, max_length=512)),
                ('identifier', models.CharField(default=vote.models.mk_identifier, max_length=64)),
                ('is_active', models.BooleanField(default=True)),
            ],
        ),
        migrations.CreateModel(
            name='Choice',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('choice_text', models.TextField()),
                ('votes', models.IntegerField(default=0)),
                ('poll', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vote.poll')),
            ],
        ),
        migrations.CreateModel(
            name='Token',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token_string', models.CharField(default=vote.models.mk_token, max_length=128)),
                ('poll', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='vote.poll')),
            ],
        ),
    ]
