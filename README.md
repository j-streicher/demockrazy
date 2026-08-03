# demockrazy

A simple token based voting system.

Someone creates a poll and supplies a list of voter mail addresses. Each address receives a
single-use token by mail. Casting a vote consumes the token and deletes it, so there is no stored
link between a voter and their vote. The poll closes automatically once every token has been used,
and only then are the results visible. The creator gets a separate management token and can close
the poll early.

## Development setup

The dev environment is a Nix flake (`nix develop`, or automatically via `direnv` — see `.envrc`).
It provides Python, Django, pytest, pytest-django and ruff.

```bash
nix develop
./manage.py migrate
./manage.py runserver
```

The app is then on <http://localhost:8000>.

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

## Configuration

`demockrazy/settings.py` holds the defaults and imports an optional `demockrazy/local_settings.py`
at the end, which is where a deployment overrides `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, the mail
server and `VOTE_SEND_MAILS`. That file is not in the repository.

With `VOTE_SEND_MAILS = False` (the default) no mail is sent — the messages are printed to stdout
instead, which is what you want locally.

## Deployment

Production is `wahlcomputer.mayflower.de`, rolled out with colmena from a separate flake, running
on SQLite. Deploying needs `./manage.py migrate` (a no-op on the current schema) and
`./manage.py collectstatic`.
