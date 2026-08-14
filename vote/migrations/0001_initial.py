# A reconstruction of the original migration that was applied in production on 2016-06-09
# (django_migrations: vote/0001_initial). The file never existed in the repository, because
# migrations/ was gitignored -- it was regenerated from the model state before 0002 and verified
# against the schema of the production database. Name and contents have to stay as they are, so that
# `migrate` is a no-op in production. Details: notes/phase-2-migrations.md

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
