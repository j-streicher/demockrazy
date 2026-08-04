"""Django-Settings für demockrazy.

Diese Datei enthält die **Defaults**. Sie sind absichtlich so gewählt, dass ein Deployment, das
nichts überschreibt, sicher hochkommt (kein DEBUG, kein eingebauter SECRET_KEY) statt bequem.

Überschrieben wird auf zwei Wegen:

1. In Produktion setzt das NixOS-Modul `mayflower.demockrazy` ein generiertes Settings-Modul
   `demockrazy_config`, das `from demockrazy.settings import *` macht und danach `SECRET_KEY`,
   `DEBUG`, `DATABASES`, `STATIC_ROOT`, `LOGGING`, die `EMAIL_*`- und `VOTE_*`-Werte setzt.
   Siehe notes/deployment.md.
2. Lokal über eine optionale `demockrazy/local_settings.py` (siehe Dateiende) oder über die
   `DEMOCKRAZY_*`-Umgebungsvariablen unten.

Wichtig für Änderungen hier: **nichts darf beim Import hart fehlschlagen.** `demockrazy_config`
setzt `SECRET_KEY` erst *nach* dem Sternchen-Import — ein `os.environ["..."]` oder ein `raise`
an dieser Stelle würde die Produktion beim Start töten.
"""

import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_flag(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Kein eingebauter Key: ein Key in einem öffentlichen Repo ist kein Key.
# Ohne gesetzte Variable wird pro Prozess ein Zufallskey erzeugt. Damit bleibt `runserver` lokal
# benutzbar, ohne dass ein Geheimnis im Repo liegt; die einzige Folge ist, dass Sessions einen
# Neustart nicht überleben. Bewusst **kein** Raise: `demockrazy_config` setzt den echten Key erst
# *nach* dem Sternchen-Import, ein Fehler an dieser Stelle würde die Produktion beim Start töten.
SECRET_KEY = os.environ.get("DEMOCKRAZY_SECRET_KEY") or secrets.token_urlsafe(64)

DEBUG = _env_flag("DEMOCKRAZY_DEBUG", default=False)

ALLOWED_HOSTS = [h for h in os.environ.get("DEMOCKRAZY_ALLOWED_HOSTS", "").split(",") if h]


# Application definition

INSTALLED_APPS = [
    "vote.apps.VoteConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "demockrazy.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "demockrazy.wsgi.application"


# Datenbank
# In Produktion überschreibt demockrazy_config den Pfad auf /var/lib/demockrazy/db.sqlite3 --
# der Code läuft dort aus dem read-only Nix-Store, BASE_DIR ist also nicht beschreibbar.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DEMOCKRAZY_DB_PATH") or BASE_DIR / "db.sqlite3",
    }
}

# Hier stand von 2016 bis 2026 ein modulweites `ATOMIC_REQUESTS = True` (Commit 154e5f6, direkt
# unter DATABASES). Django liest die Option aber **pro Datenbank**, aus
# `DATABASES['default']['ATOMIC_REQUESTS']` -- ein modulweiter Wert wird nie gelesen. Gemessen:
# `connections.settings['default']['ATOMIC_REQUESTS']` war die ganze Zeit `False`. Produktion hätte
# den Wert ohnehin verloren, weil das generierte `demockrazy_config` `DATABASES` komplett neu setzt.
#
# Entfernt statt an die richtige Stelle verschoben, weil Einschalten eine echte
# Verhaltensänderung wäre -- und zwar in der riskantesten Richtung: dann nähme *jeder* Request eine
# Transaktion auf einer SQLite-Datei, die vier uwsgi-Prozesse teilen (B13), auch die reine
# Ergebnisseite. Wo Atomarität gebraucht wird, steht sie explizit im Code und ist getestet:
# `vote.services.polls.create_poll()` und der `atomic()`-Block in `vote.views.vote()`, der die
# Teilstimme eines unvollständigen Multiple-Choice-POST zurücknimmt. Beides lief nie über diese
# Option. Festgehalten in demockrazy/tests/test_transactions.py.

# Die Tabellen stammen von 2015/16 und haben AutoField-Primärschlüssel. Explizit denselben Wert
# setzen, statt Djangos neuen BigAutoField-Default zu übernehmen: das vermeidet eine
# AlterField-Migration, die auf SQLite alle drei Tabellen neu schreiben würde -- für exakt null
# Gewinn, weil SQLite-Integer-Primärschlüssel ohnehin 64-bittig sind.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"


# Password validation
# https://docs.djangoproject.com/en/1.9/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/1.9/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

# USE_L10N ist seit Django 5.0 entfernt und wurde stillschweigend ignoriert.

USE_TZ = True


# Statische Dateien. In Produktion serviert nginx STATIC_ROOT direkt aus
# /var/lib/demockrazy/static, wohin demockrazy_config es umbiegt.
STATIC_URL = "/static/"
STATIC_ROOT = os.environ.get("DEMOCKRAZY_STATIC_ROOT") or BASE_DIR / "static"

# Gehashte Dateinamen (`bootstrap.a1b2c3d4.css`), damit ein Deploy nicht darauf angewiesen ist, dass
# Browser und Proxies eine alte Datei loslassen. **Kein Whitenoise:** nginx serviert STATIC_ROOT
# direkt, das soll so bleiben -- gebraucht wird nur der Dateiname, nicht ein zweiter Server.
#
# Zwei Dinge, die das gefahrlos machen: `collectstatic --noinput` läuft im `preStart` bei *jedem*
# Service-Start, das Manifest ist also nie veraltet; und bei DEBUG=True hasht Django gar nicht
# (`HashedFilesMixin._url`), `runserver` braucht deshalb kein collectstatic.
# Die Testsuite setzt das bewusst zurück -- sie soll nicht von einem collectstatic-Lauf abhängen,
# siehe test_settings.py.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
    },
}

EMAIL_HOST = ""
EMAIL_PORT = 25
# EMAIL_HOST_USER = "derp"
# EMAIL_HOST_PASSWORD = "derp"
EMAIL_USE_TLS = True
EMAIL_USE_SSL = False

VOTE_MAIL_FROM = "wahlleitung@demo.ckrazy"
VOTE_BASE_URL = "http://127.0.0.1:8000"
VOTE_SEND_MAILS = _env_flag("DEMOCKRAZY_SEND_MAILS", default=False)


# Optionale lokale Overrides für die Entwicklung. In Produktion nicht im Spiel -- dort läuft
# demockrazy_config, das diese Datei ersetzt (notes/deployment.md).
# Kein print im except-Zweig: das Fehlen der Datei ist der Normalfall und landete bei jedem
# Produktionsstart im Syslog.
try:
    from .local_settings import *
except ImportError:
    pass
