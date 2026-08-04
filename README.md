# demockrazy

A simple token based voting system.

Someone creates a poll and supplies a list of voter mail addresses. Each address receives a
single-use token by mail. Casting a vote consumes the token and deletes it, so there is no stored
link between a voter and their vote. The poll closes automatically once every token has been used,
and only then are the results visible. The creator gets a separate management token and can close
the poll early.

The invitation mail links to `/vote/<poll>/?token=<token>`. On the first request that token is moved
into a path-scoped, `HttpOnly` cookie and the browser is redirected to the same address **without the
query string**, so the token stops appearing in access logs, `Referer` headers and browser history.
Old links keep working unchanged, and casting a vote still reads the token from the submitted form,
not from the cookie.

## Development setup

The dev environment is a Nix flake (`nix develop`, or automatically via `direnv` — see `.envrc`).
It provides Python, Django, pytest, pytest-django and ruff.

```bash
nix develop
./manage.py migrate --settings=demockrazy.dev_settings
./manage.py runserver --settings=demockrazy.dev_settings
```

The app is then on <http://localhost:8000>. Mails are printed to the console.

`demockrazy/settings.py` defaults to `DEBUG = False` and has no built-in `SECRET_KEY`, so a
deployment that configures nothing comes up safely rather than conveniently — which is also why
plain `runserver` refuses to start. `demockrazy/dev_settings.py` is the documented way around it;
`DEMOCKRAZY_DEBUG=1 ./manage.py runserver` does the same via the environment.

Without Nix, install the dependencies from `pyproject.toml` (Django 5.2 and, for development,
pytest, pytest-django and ruff) into a virtualenv; the `manage.py` commands are the same.

Do **not** run `makemigrations` as a setup step. The migrations are committed and reflect the
schema that production actually runs — see `notes/phase-2-migrations.md` for why that matters.

## Tests and linting

```bash
pytest
ruff check .
ruff format --check .
```

The suite runs against `demockrazy/test_settings.py` (in-memory SQLite, mails captured in
`django.core.mail.outbox`), so it is independent of any local configuration.

`vote/tests/test_known_bugs.py` holds known defects written as the behaviour that *should* hold,
each marked `xfail(strict=True)`. Fixing one of them turns the suite red — that is the reminder to
remove the marker.

`.github/workflows/checks.yml` runs the same commands on every push, plus `manage.py check`,
`manage.py makemigrations --check --dry-run` and `nix flake check`.

## Configuration

`demockrazy/settings.py` holds the defaults. Three ways to override them, in the order they apply:

- `DEMOCKRAZY_*` environment variables — `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `DB_PATH`,
  `STATIC_ROOT`, `SEND_MAILS`.
- An optional `demockrazy/local_settings.py`, imported at the end of `settings.py` if present.
  Not in the repository.
- A settings module that imports `demockrazy.settings` and overrides it, selected via
  `DJANGO_SETTINGS_MODULE`. This is what production does.

With `VOTE_SEND_MAILS = False` (the default) no mail is sent — the messages are printed instead,
which is what you want locally.

The wording of the mails is not configuration: it lives in `vote/templates/vote/mail/`. Those
templates disable autoescaping (they are plain text) and end without a trailing newline, both
deliberately — `vote/tests/test_mail_service.py` pins the exact output.

## Frontend

Bootstrap 5.3.8 and Chart.js 4.5.1 are vendored under `vote/static/`, deliberately not loaded from a
CDN: the pages should work without a connection to any foreign host. There is no build step and no
JavaScript dependency beyond those two — Bootstrap 5 needs no jQuery. Chart.js is loaded by
`results.html` only, not by `base.html`, because one of the six pages draws a chart.

Both are MIT, as is this repository. That is not incidental: the chart library used to be Highcharts,
which has no free licence for commercial use.

Each vendored directory carries a `PROVENANCE.md` — read it before touching those files. They are not
byte-identical to upstream: the `sourceMappingURL` comment is removed from each bundle, because
`collectstatic` aborts on a reference to the `.map` files, which are not vendored. It runs on every
service start, so an abort keeps the service from coming up.

Static file names are hashed via `ManifestStaticFilesStorage`. `collectstatic` writes the manifest;
with `DEBUG = True` Django skips hashing, so `runserver` needs no `collectstatic`.

## Deployment

Production is `wahlcomputer.mayflower.de`, rolled out with colmena and running on SQLite. The
`mayflower.demockrazy` NixOS module lives outside this repository; it pins this repo at a specific
revision, generates a `demockrazy_config` settings module from its options, and runs the app under
uwsgi behind nginx. Its `preStart` runs `migrate` and `collectstatic`.

Two consequences worth knowing before changing anything here:

- Updating the application in production requires bumping `rev` and `sha256` in that module.
  Nothing in this repository moves production on its own.
- The Django version comes from the nixpkgs that evaluates the host, not from `pyproject.toml`.
  This file documents the requirement; it does not enforce it.

The database is SQLite, and four uwsgi processes share the one file. `DATABASES['default']
['OPTIONS']` therefore sets `transaction_mode='IMMEDIATE'`, WAL journalling and a 20 second
`timeout`. `IMMEDIATE` is the one that matters: with Django's `DEFERRED` default, a transaction that
reads before it writes has to upgrade its lock, and SQLite cannot make that wait -- it returns
`SQLITE_BUSY` at once, ignoring `timeout`. Measured with 8 concurrent read-then-write transactions
x 25 rounds: 36 of 200 succeed on the defaults, 200 of 200 with these options.

Those options do not reach production on their own. A settings module that replaces `DATABASES`
wholesale drops them, which is what production's generated module does. `manage.py check` reports
their absence, so run it against the real settings after deploying:

```
DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check
```

`GET /healthz` returns `200 ok` when the process can serve requests and read the database, and
`503 database unavailable` when it cannot. It deliberately does not test writability: that would
mean writing on every probe, and with four uwsgi processes on one SQLite file the check would become
a cause of the lock errors it is meant to report. Point monitoring at it with a `Host` header that
`ALLOWED_HOSTS` accepts — a probe against `localhost` gets a 400 and looks like an outage.

See `notes/deployment.md` for the full analysis, including two settings changes that would break
production if made naively.
