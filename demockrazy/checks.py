"""System checks that make silent misconfiguration visible.

This file exists because of a lesson from two findings in this project: `ATOMIC_REQUESTS` was
ineffective for ten years (B16), and `.gitignore` swallowed the frontend assets for ten years (B18).
Both had the same property -- **they looked right and did nothing**, without a message appearing
anywhere.

The SQLite hardening from 5.4 can end the same way: it lives in `DATABASES['OPTIONS']`, and the
generated `demockrazy_config` sets `DATABASES` from scratch in production. This check makes its
absence visible instead of leaving it to the next `database is locked`.

Checkable after a deploy with:

    DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check
"""

from django.conf import settings
from django.core.checks import Warning, register

HINT = (
    "Ohne transaction_mode='IMMEDIATE' liefert SQLite ein sofortiges SQLITE_BUSY, wenn eine "
    "Transaktion von Lesen auf Schreiben hochstufen muss -- der timeout greift dann nicht. Mit "
    "vier uwsgi-Prozessen auf einer Datei sind das die 'database is locked'-Fehler aus B13. "
    "Gemessen: 164 von 200 gleichzeitigen Stimmabgaben scheiterten daran. Die Werte stehen als "
    "Default in demockrazy/settings.py. Schlaegt dieser Check an, hat ein ueberschreibendes "
    "Settings-Modul DATABASES neu gesetzt und sie dabei verloren -- dann gehoeren sie dorthin (in "
    "Produktion: ins NixOS-Modul bzw. in dessen djangoSettings-Option)."
)


def _is_file_backed_sqlite(config):
    """SQLite on a file -- locks only exist there, and WAL only has an effect there."""
    if "sqlite3" not in config.get("ENGINE", ""):
        return False
    name = str(config.get("NAME", ""))
    # In-memory knows no WAL (`journal_mode` stays `memory` there) and has no concurrency between
    # processes. The test suite runs that way -- the check must not complain about it.
    return name != ":memory:" and "mode=memory" not in name


def problems_for(alias, config):
    """Checks *one* `DATABASES` entry. A pure function, so it is testable without settings.

    The detour is deliberate: a test that overrides `settings.DATABASES` earns a `UserWarning` from
    Django ("can lead to unexpected behavior") -- rightly so, because the open connections depend on
    it. Here there is nothing to override.
    """
    if not _is_file_backed_sqlite(config):
        return []

    options = config.get("OPTIONS") or {}
    missing = []
    if "journal_mode=wal" not in str(options.get("init_command", "")).lower().replace(" ", ""):
        missing.append("init_command mit 'PRAGMA journal_mode=WAL;'")
    # Check the **value**, not its presence (review R9-1). Before, any truthy value was enough:
    # `DEFERRED` -- exactly the state 5.4 abolished -- and a typo both got through. A check against
    # silent misconfiguration that is itself silent is error class K1 applied to itself.
    if str(options.get("transaction_mode", "")).strip().upper() != "IMMEDIATE":
        missing.append("transaction_mode='IMMEDIATE'")
    timeout = options.get("timeout")
    if not isinstance(timeout, int | float) or timeout <= 0:
        missing.append("timeout > 0 (sqlite3-Default sind 5 s)")
    if not missing:
        return []

    return [
        Warning(
            f"DATABASES[{alias!r}] ist SQLite auf einer Datei, ohne die Härtung aus Plan 5.4. "
            f"Es fehlt: {', '.join(missing)}.",
            hint=HINT,
            id="demockrazy.W001",
        )
    ]


@register()
def check_sqlite_concurrency_options(app_configs, **kwargs):
    """Reports every SQLite database that lacks the hardening from plan 5.4.

    Deliberately **without** `Tags.database`: `manage.py check` skips checks tagged that way when no
    `--database` is given, and then the check would be silent in exactly the moment it is meant for.
    It only reads the settings and opens no connection.
    """
    problems = []
    for alias, config in settings.DATABASES.items():
        problems.extend(problems_for(alias, config))
    return problems
