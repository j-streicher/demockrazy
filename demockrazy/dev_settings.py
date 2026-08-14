"""Settings for local development.

`settings.py` deliberately has production-safe defaults (`DEBUG = False`, no built-in `SECRET_KEY`),
which means `runserver` does not start on its own -- Django then demands a non-empty
`ALLOWED_HOSTS`. This module is the documented way around that:

    ./manage.py runserver --settings=demockrazy.dev_settings

Alternatively through the environment, without this module:

    DEMOCKRAZY_DEBUG=1 ./manage.py runserver

Production is untouched by this -- there the systemd service sets
`DJANGO_SETTINGS_MODULE=demockrazy_config` (see notes/deployment.md).
"""

from .settings import *  # noqa: F403

DEBUG = True

# With DEBUG=True Django allows localhost automatically; being explicit is clearer anyway.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Mails to the console instead of into the world. VOTE_SEND_MAILS has to be True for the views to
# call send_mail() at all -- otherwise they only print the arguments.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
VOTE_SEND_MAILS = True
