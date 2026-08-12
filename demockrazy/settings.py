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


def _env_int(name, default):
    """Wie `_env_flag`, nur für Zahlen. Ein unbrauchbarer Wert fällt auf den Default zurück.

    Bewusst ohne Raise: `demockrazy_config` importiert diese Datei per Sternchen-Import, und ein
    Fehler hier tötet den Service beim Start (siehe Modulkommentar oben).
    """
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


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
#
# ⚠️ **Diese OPTIONS erreichen Produktion nicht von allein** (Plan 5.4). `demockrazy_config` setzt
# `DATABASES` *komplett neu* und verliert damit alles, was hier drinsteht -- genau der Mechanismus,
# über den `ATOMIC_REQUESTS` zehn Jahre wirkungslos war (B16). Damit das nicht wieder still
# passiert, meldet ein System-Check das Fehlen: `manage.py check` (siehe demockrazy/checks.py).
# Prüfen lässt sich das gegen die echten Prod-Settings mit
# `DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check`.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DEMOCKRAZY_DB_PATH") or BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Vier uwsgi-Prozesse teilen eine Datei (B13). Ohne diese drei Optionen sind
            # `database is locked`-Fehler bei gleichzeitiger Stimmabgabe realistisch.
            #
            # `transaction_mode` ist der wichtigste Punkt und nicht der offensichtlichste:
            # Djangos Default ist `DEFERRED`, da nimmt SQLite die Schreibsperre erst beim ersten
            # Schreibzugriff. Fängt eine Transaktion mit einem SELECT an und schreibt danach --
            # genau der Ablauf in `vote()` --, muss die Leseperre zur Schreibsperre hochgestuft
            # werden, und **das kann SQLite nicht warten lassen**: es kommt ein sofortiges
            # `SQLITE_BUSY`, ohne `timeout` zu beachten. `IMMEDIATE` nimmt die Schreibsperre schon
            # beim BEGIN, damit greift der `timeout` und die Schreiber stellen sich in eine Reihe.
            #
            # Das ist nur deshalb billig, weil `ATOMIC_REQUESTS` aus bleibt (F18): `atomic()` gibt
            # es genau an den zwei Stellen, die wirklich schreiben. Mit ATOMIC_REQUESTS würde
            # `IMMEDIATE` *jeden* Request serialisieren, auch die Ergebnisseite.
            "transaction_mode": "IMMEDIATE",
            # WAL: Leser blockieren den Schreiber nicht mehr und umgekehrt. Die Einstellung hängt
            # an der *Datei*, nicht an der Verbindung -- ab dem zweiten Verbindungsaufbau ist das
            # PRAGMA ein No-op. Legt `db.sqlite3-wal` und `-shm` daneben; das Verzeichnis
            # /var/lib/demockrazy ist beschreibbar, und borg sichert es mit.
            "init_command": "PRAGMA journal_mode=WAL;",
            # `sqlite3`-Default sind 5 s. **Bewusst nicht `synchronous=NORMAL` dazu**, was sonst
            # gern mit WAL zusammen empfohlen wird: das erkauft Geschwindigkeit damit, dass ein
            # Stromausfall die letzten Commits verlieren kann. Hier sind Commits *Stimmen*.
            "timeout": 20,
        },
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

# Djangos Default ist `EMAIL_TIMEOUT = None`, und dann bekommt der Socket **keine** Zeitgrenze --
# nachgesehen statt vermutet: das Backend gibt `timeout` gar nicht an `smtplib` weiter, `smtplib`
# nimmt den Socket-Default, und `socket.getdefaulttimeout()` ist ebenfalls `None`. Ein Mailserver,
# der die Verbindung annimmt und dann schweigt, blockiert den Aufrufer damit **unbegrenzt**.
#
# Das ist heute schon relevant, nicht erst für Ziel 2: der Versand läuft synchron im Request
# (siehe notes/plan.md §11), ein hängender Server hält also einen uwsgi-Prozess -- und es gibt
# vier. Für den getakteten Versender (§11.7) kommt hinzu, dass er sich selbst sperrt: ein Lauf,
# der nie endet, hält die Sperre und es geht überhaupt keine Mail mehr raus.
#
# 10 s sind großzügig für einen Mailserver im selben Netz und trotzdem endlich.
EMAIL_TIMEOUT = _env_int("DEMOCKRAZY_MAIL_TIMEOUT", 10)

VOTE_MAIL_FROM = "wahlleitung@demo.ckrazy"
VOTE_BASE_URL = "http://127.0.0.1:8000"
VOTE_SEND_MAILS = _env_flag("DEMOCKRAZY_SEND_MAILS", default=False)

# Obergrenze für Empfänger pro Umfrage (B4, Plan 3.8). `/vote/create` hat keine Authentifizierung:
# ohne Deckel kann jeder im Netz beliebig viele Mails über den SMTP-Account verschicken.
#
# 150 ist vom User gewählt und liegt über den real vorkommenden 60--100. Der Wert ist
# **Missbrauchsschutz, keine Lösung für das Rate-Limit des Mailservers**: der antwortet schon ab
# etwa 50 Nachrichten pro Zeitfenster mit `450 4.7.1 Error: too much mail from`. Eine Umfrage mit
# 150 Empfängern ist also erlaubt, aber erst mit dem getakteten Versand (Ziel 2) zustellbar.
# Gezählt werden die **deduplizierten** Adressen -- was zählt, ist die Zahl der Mails.
VOTE_MAX_RECIPIENTS = _env_int("DEMOCKRAZY_MAX_RECIPIENTS", 150)

# Obergrenze für Antwortmöglichkeiten pro Umfrage (Review R7-1). Dasselbe Motiv wie beim
# Empfänger-Deckel: `/vote/create` ist unauthentifiziert, und ohne Grenze wurden 5 000 Choices
# angenommen -- eine Seite von 1,3 MB pro Aufruf und bei multiple_choice 5 000 UPDATEs unter der
# SQLite-Schreibsperre. **Der Wert ist von mir gesetzt, nicht vom User**, anders als die 150; real
# vorkommende Umfragen haben eine Handvoll. Über 1 000 wäre eine multiple_choice-Umfrage ohnehin
# nicht mehr abstimmbar, weil das Formular dann mehr Felder schickt als
# `DATA_UPLOAD_MAX_NUMBER_FIELDS` erlaubt.
VOTE_MAX_CHOICES = _env_int("DEMOCKRAZY_MAX_CHOICES", 100)

# Taktung des Versands (Plan §11.7). Beide Werte sind vom User vorgegeben: 30er Batches, 2 Sekunden
# dazwischen. Sie stehen hier und nicht als Konstanten im Code, weil sie **die Schraube** sind, an
# der man dreht, wenn der Mailserver wieder mit `450 4.7.1 Error: too much mail from` antwortet.
#
# ⚠️ Die Rechnung dazu gehört daneben: 100 Empfänger sind vier Batches, mit 2 s Pause also nach
# ~7 s durch -- **alle 101 Nachrichten liegen damit im selben Zeitfenster.** Immer erfolgreich
# gemessen wurden 30 pro Fenster, den `450` gab es bei 50. Ist das Zählfenster die Postfix-Vorgabe
# von 60 s (das ist F20), kommt der Fehler also wieder. Verloren geht dadurch nichts -- ein `450`
# ist ein 4xx, der Versender bricht ab und der nächste Timer-Aufruf trifft ein zurückgesetztes
# Fenster --, es kostet nur Zeit und Logzeilen. **Wenn das passiert: `DEMOCKRAZY_MAIL_BATCH_PAUSE`
# auf 60.** Das ist eine Zahl und kein Deploy.
VOTE_MAIL_BATCH_SIZE = _env_int("DEMOCKRAZY_MAIL_BATCH_SIZE", 30)
VOTE_MAIL_BATCH_PAUSE = _env_int("DEMOCKRAZY_MAIL_BATCH_PAUSE", 2)


# Optionale lokale Overrides für die Entwicklung. In Produktion nicht im Spiel -- dort läuft
# demockrazy_config, das diese Datei ersetzt (notes/deployment.md).
# Kein print im except-Zweig: das Fehlen der Datei ist der Normalfall und landete bei jedem
# Produktionsstart im Syslog.
try:
    from .local_settings import *
except ImportError:
    pass
