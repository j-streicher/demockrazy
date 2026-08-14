"""Settings for the test suite.

Deliberately explicit: `settings.py` imports an optional `local_settings.py` at the end, and on a
developer machine that can contain anything. Everything relevant to tests is overridden here
afterwards, so that the suite runs independently of the local configuration.
"""

from .settings import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-only-not-a-secret"
ALLOWED_HOSTS = ["testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Mails land in django.core.mail.outbox instead of on stdout. VOTE_SEND_MAILS has to be True for the
# views to call send_mail() at all -- otherwise they would only print.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
VOTE_SEND_MAILS = True
VOTE_BASE_URL = "http://testserver"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Without this, 56 tests fail with `Missing staticfiles manifest entry` (measured, not feared):
# `settings.py` has switched to ManifestStaticFilesStorage since 4.4, and DEBUG=False here -- so
# Django looks in the manifest, which only `collectstatic` writes. The suite should not depend on a
# collectstatic run, and what `{% static %}` emits is not its subject. What cache busting achieves
# is checked specifically by demockrazy/tests/test_staticfiles.py.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
