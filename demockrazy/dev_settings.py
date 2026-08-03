"""Settings für die lokale Entwicklung.

`settings.py` hat bewusst produktionssichere Defaults (`DEBUG = False`, kein eingebauter
`SECRET_KEY`), womit `runserver` ohne Zutun nicht startet -- Django verlangt dann ein gefülltes
`ALLOWED_HOSTS`. Dieses Modul ist der dokumentierte Weg drumherum:

    ./manage.py runserver --settings=demockrazy.dev_settings

Alternativ über die Umgebung, ohne dieses Modul:

    DEMOCKRAZY_DEBUG=1 ./manage.py runserver

Produktion ist davon unberührt -- dort setzt der systemd-Service
`DJANGO_SETTINGS_MODULE=demockrazy_config` (siehe notes/deployment.md).
"""

from .settings import *  # noqa: F403

DEBUG = True

# Bei DEBUG=True erlaubt Django localhost automatisch; explizit ist trotzdem klarer.
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Mails auf die Konsole statt in die Welt. VOTE_SEND_MAILS muss True sein, damit die Views
# überhaupt send_mail() aufrufen -- sonst printen sie nur die Argumente.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
VOTE_SEND_MAILS = True
