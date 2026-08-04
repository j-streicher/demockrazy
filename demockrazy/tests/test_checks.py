"""Tests für den System-Check aus demockrazy/checks.py (Plan 5.4).

Der Check ist ein Sicherheitsnetz gegen genau den Mechanismus, der `ATOMIC_REQUESTS` zehn Jahre
wirkungslos gemacht hat (B16): ein überschreibendes Settings-Modul setzt `DATABASES` neu und
verliert die `OPTIONS`. Ein Netz, das selbst ungetestet ist, ist keines.

Geprüft wird `problems_for()` statt der registrierten Funktion, damit kein Test `settings.DATABASES`
überschreiben muss -- das quittiert Django mit einem `UserWarning`, und zu Recht.
"""

from demockrazy.checks import check_sqlite_concurrency_options, problems_for

GEHAERTET = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": "/var/lib/demockrazy/db.sqlite3",
    "OPTIONS": {
        "transaction_mode": "IMMEDIATE",
        "init_command": "PRAGMA journal_mode=WAL;",
        "timeout": 20,
    },
}


def test_repo_defaults_pass():
    """Die Werte aus settings.py müssen den Check bestehen -- sonst wäre `manage.py check` rot.

    Das ist zugleich der einzige Test, der die *registrierte* Funktion aufruft, also auch prüft,
    dass sie über `settings.DATABASES` läuft und nicht ins Leere greift.
    """
    assert check_sqlite_concurrency_options(app_configs=None) == []


def test_hardened_file_database_passes():
    assert problems_for("default", GEHAERTET) == []


def test_bare_file_database_is_flagged():
    """Der Fall, für den der Check existiert: Prod setzt DATABASES neu und lässt OPTIONS weg."""
    problems = problems_for("default", {k: v for k, v in GEHAERTET.items() if k != "OPTIONS"})
    assert len(problems) == 1
    assert problems[0].id == "demockrazy.W001"
    # Die Meldung muss sagen, *was* fehlt -- sonst hilft sie nicht weiter.
    for erwartet in ("journal_mode", "timeout", "transaction_mode"):
        assert erwartet in problems[0].msg


def test_names_only_what_is_missing():
    config = dict(GEHAERTET, OPTIONS={"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"})
    problems = problems_for("default", config)
    assert len(problems) == 1
    assert "transaction_mode" in problems[0].msg
    assert "journal_mode" not in problems[0].msg
    assert "timeout" not in problems[0].msg


def test_in_memory_database_is_left_alone():
    """Die Testsuite läuft auf :memory: -- dort gibt es kein WAL und keine Nebenläufigkeit.

    Ohne diese Ausnahme würde der Check die eigene Suite anmeckern.
    """
    assert (
        problems_for("default", {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}) == []
    )


def test_other_backends_are_left_alone():
    """Auf Postgres (das `postgres`-Extra existiert) hat nichts davon eine Bedeutung."""
    config = {"ENGINE": "django.db.backends.postgresql", "NAME": "demockrazy"}
    assert problems_for("default", config) == []
