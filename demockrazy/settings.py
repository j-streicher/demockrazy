"""Django settings for demockrazy.

This file holds the **defaults**. They are deliberately chosen so that a deployment overriding
nothing comes up safely (no DEBUG, no built-in SECRET_KEY) rather than conveniently.

There are two ways they get overridden:

1. In production the NixOS module `mayflower.demockrazy` installs a generated settings module
  `demockrazy_config`, which does `from demockrazy.settings import *` and then sets `SECRET_KEY`,
  `DEBUG`, `DATABASES`, `STATIC_ROOT`, `LOGGING`, and the `EMAIL_*` and `VOTE_*` values. See
  notes/deployment.md.
2. Locally through an optional `demockrazy/local_settings.py` (see the end of the file) or through
  the `DEMOCKRAZY_*` environment variables below.

Important when changing anything here: **nothing may fail hard at import time.** `demockrazy_config`
sets `SECRET_KEY` only *after* the star import — an `os.environ["..."]` or a `raise` at this point
would kill production on start.
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
    """Like `_env_flag`, only for numbers. An unusable value falls back to the default.

    Deliberately without a raise: `demockrazy_config` imports this file with a star import, and an
    error here kills the service on start (see the module comment above).
    """
    try:
        return int(os.environ[name])
    except (KeyError, ValueError):
        return default


# No built-in key: a key in a public repository is not a key. Without the variable set, a random key
# is generated per process. That keeps `runserver` usable locally without a secret sitting in the
# repository; the only consequence is that sessions do not survive a restart. Deliberately **no**
# raise: `demockrazy_config` sets the real key only *after* the star import, so an error at this
# point would kill production on start.
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


# Database In production demockrazy_config overrides the path to /var/lib/demockrazy/db.sqlite3 --
# the code runs there out of the read-only Nix store, so BASE_DIR is not writable.
#
# ⚠️ **These OPTIONS do not reach production on their own** (plan 5.4). `demockrazy_config` sets
# `DATABASES` *from scratch* and thereby loses everything in here -- exactly the mechanism that left
# `ATOMIC_REQUESTS` ineffective for ten years (B16). So that this cannot happen silently again, a
# system check reports their absence: `manage.py check` (see demockrazy/checks.py). It can be
# checked against the real production settings with `DJANGO_SETTINGS_MODULE=demockrazy_config
# python3 manage.py check`.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DEMOCKRAZY_DB_PATH") or BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            # Four uwsgi processes share one file (B13). Without these three options,
            # `database is locked` errors during concurrent voting are realistic.
            #
            # `transaction_mode` is the most important point and not the most obvious one: Django's
            # default is `DEFERRED`, where SQLite takes the write lock only on the first write. If a
            # transaction starts with a SELECT and writes afterwards -- exactly what happens in
            # `vote()` -- the read lock has to be upgraded to a write lock, and **SQLite cannot make
            # that wait**: an immediate `SQLITE_BUSY` comes back, ignoring `timeout`. `IMMEDIATE`
            # takes the write lock at BEGIN, so `timeout` applies and the writers queue up.
            #
            # This is only cheap because `ATOMIC_REQUESTS` stays off (F18): `atomic()` exists at
            # exactly the two places that really write. With ATOMIC_REQUESTS, `IMMEDIATE` would
            # serialise *every* request, the results page included.
            "transaction_mode": "IMMEDIATE",
            # WAL: readers no longer block the writer and vice versa. The setting belongs to the
            # *file*, not to the connection -- from the second connection onwards the PRAGMA is a
            # no-op. It puts `db.sqlite3-wal` and `-shm` next to the database; the directory
            # /var/lib/demockrazy is writable, and borg backs it up along with the rest.
            "init_command": "PRAGMA journal_mode=WAL;",
            # The `sqlite3` default is 5 s. **Deliberately no `synchronous=NORMAL` alongside it**,
            # which is otherwise often recommended together with WAL: it buys speed by allowing a
            # power failure to lose the last commits. Here commits are *votes*.
            "timeout": 20,
        },
    }
}

# From 2016 to 2026 a module-wide `ATOMIC_REQUESTS = True` stood here (commit 154e5f6, directly
# below DATABASES). Django reads the option **per database**, though, from
# `DATABASES['default']['ATOMIC_REQUESTS']` -- a module-wide value is never read. Measured:
# `connections.settings['default']['ATOMIC_REQUESTS']` was `False` the entire time. Production would
# have lost the value anyway, because the generated `demockrazy_config` sets `DATABASES` from
# scratch.
#
# Removed rather than moved to the right place, because switching it on would be a real change in
# behaviour -- and in the riskiest direction: *every* request would then take a transaction on a
# SQLite file shared by four uwsgi processes (B13), the plain results page included. Where atomicity
# is needed it is explicit in the code and tested: `vote.services.polls.create_poll()` and the
# `atomic()` block in `vote.views.vote()`, which takes back the partial vote of an incomplete
# multiple-choice POST. Neither ever went through this option. Recorded in
# demockrazy/tests/test_transactions.py.

# The tables date from 2015/16 and have AutoField primary keys. Setting the same value explicitly
# instead of taking Django's new BigAutoField default: that avoids an AlterField migration which on
# SQLite would rewrite all three tables -- for exactly no gain, because SQLite integer primary keys
# are 64-bit anyway.
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

# USE_L10N was removed in Django 5.0 and had been silently ignored.

USE_TZ = True


# Static files. In production nginx serves STATIC_ROOT directly out of /var/lib/demockrazy/static,
# where demockrazy_config points it.
STATIC_URL = "/static/"
STATIC_ROOT = os.environ.get("DEMOCKRAZY_STATIC_ROOT") or BASE_DIR / "static"

# Hashed file names (`bootstrap.a1b2c3d4.css`), so that a deploy does not depend on browsers and
# proxies letting go of an old file. **No Whitenoise:** nginx serves STATIC_ROOT directly and should
# keep doing so -- all that is needed is the file name, not a second server.
#
# Two things make this safe: `collectstatic --noinput` runs in `preStart` on *every* service start,
# so the manifest is never stale; and with DEBUG=True Django does not hash at all
# (`HashedFilesMixin._url`), which is why `runserver` needs no collectstatic. The test suite
# deliberately resets this -- it should not depend on a collectstatic run, see test_settings.py.
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

# Django's default is `EMAIL_TIMEOUT = None`, and then the socket gets **no** time limit -- looked
# up rather than assumed: the backend does not pass `timeout` to `smtplib` at all, `smtplib` takes
# the socket default, and `socket.getdefaulttimeout()` is `None` as well. A mail server that accepts
# the connection and then goes quiet therefore blocks the caller **indefinitely**.
#
# This matters today, not only for goal 2: sending runs synchronously in the request (see
# notes/plan.md §11), so a hanging server holds a uwsgi process -- and there are four. For the paced
# sender (§11.7) there is more: it locks itself out. A run that never ends holds the lock, and then
# no mail goes out at all.
#
# 10 s is generous for a mail server on the same network and still finite.
EMAIL_TIMEOUT = _env_int("DEMOCKRAZY_MAIL_TIMEOUT", 10)

VOTE_MAIL_FROM = "wahlleitung@demo.ckrazy"
VOTE_BASE_URL = "http://127.0.0.1:8000"
VOTE_SEND_MAILS = _env_flag("DEMOCKRAZY_SEND_MAILS", default=False)

# Upper bound on recipients per poll (B4, plan 3.8). `/vote/create` has no authentication: without a
# cap, anyone on the network can send arbitrarily many mails through the SMTP account.
#
# 150 was chosen by the user and is above the 60--100 that actually occur. The value is **protection
# against abuse, not a solution for the mail server's rate limit**: that one starts answering
# `450 4.7.1 Error: too much mail from` at around 50 messages per window. So a poll with 150
# recipients is allowed, but only deliverable with the paced sender (goal 2).
# The **deduplicated** addresses are counted -- what matters is the number of mails.
VOTE_MAX_RECIPIENTS = _env_int("DEMOCKRAZY_MAX_RECIPIENTS", 150)

# Upper bound on choices per poll (review R7-1). The same motive as the recipient cap:
# `/vote/create` is unauthenticated, and without a limit 5,000 choices were accepted -- a page of
# 1.3 MB per request and, with multiple_choice, 5,000 UPDATEs under the SQLite write lock. **This
# value was set by me, not by the user**, unlike the 150; polls that actually occur have a handful.
# Above 1,000 a multiple_choice poll would not be votable anyway, because the form then sends more
# fields than `DATA_UPLOAD_MAX_NUMBER_FIELDS` allows.
VOTE_MAX_CHOICES = _env_int("DEMOCKRAZY_MAX_CHOICES", 100)

# The pacing of the sender (plan §11.7). Both values were given by the user: batches of 30, 2
# seconds in between. They live here and not as constants in the code because they are **the screw**
# to turn when the mail server answers `450 4.7.1 Error: too much mail from` again.
#
# ⚠️ The arithmetic belongs next to them: 100 recipients are four batches, so with a 2 s pause they
# are through after ~7 s -- **which puts all 101 messages in the same window.** 30 per window was
# measured as always succeeding, the `450` came at 50. So if the counting window is Postfix's
# default of 60 s (that is F20), the error comes back. Nothing is lost by it -- a `450` is a 4xx,
# the sender stops and the next timer invocation meets a window that has been reset -- it only costs
# time and log lines. **If that happens: `DEMOCKRAZY_MAIL_BATCH_PAUSE` to 60.** That is a number,
# not a deploy.
VOTE_MAIL_BATCH_SIZE = _env_int("DEMOCKRAZY_MAIL_BATCH_SIZE", 30)
VOTE_MAIL_BATCH_PAUSE = _env_int("DEMOCKRAZY_MAIL_BATCH_PAUSE", 2)


# Optional local overrides for development. Not in play in production -- demockrazy_config runs
# there and replaces this file (notes/deployment.md). No print in the except branch: the file being
# absent is the normal case, and it used to land in the syslog on every production start.
try:
    from .local_settings import *
except ImportError:
    pass
