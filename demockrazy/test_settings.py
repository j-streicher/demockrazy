"""Settings für die Testsuite.

Bewusst explizit: `settings.py` importiert am Ende ein optionales `local_settings.py`, und auf
einem Entwicklerrechner kann darin alles stehen. Alles, was für Tests relevant ist, wird hier
danach überschrieben, damit die Suite unabhängig von der lokalen Konfiguration läuft.
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

# Mails landen in django.core.mail.outbox statt auf stdout. VOTE_SEND_MAILS muss True sein,
# damit die Views überhaupt send_mail() aufrufen -- sonst würden sie nur printen.
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
VOTE_SEND_MAILS = True
VOTE_BASE_URL = "http://testserver"

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
