"""Tests for the system check from demockrazy/checks.py (plan 5.4).

The check is a safety net against exactly the mechanism that left `ATOMIC_REQUESTS` ineffective for
ten years (B16): an overriding settings module sets `DATABASES` anew and loses the `OPTIONS`. A net
that is itself untested is not one.

`problems_for()` is checked rather than the registered function, so that no test has to override
`settings.DATABASES` -- Django answers that with a `UserWarning`, and rightly so.
"""

from demockrazy.checks import check_sqlite_concurrency_options, problems_for

HARDENED = {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": "/var/lib/demockrazy/db.sqlite3",
    "OPTIONS": {
        "transaction_mode": "IMMEDIATE",
        "init_command": "PRAGMA journal_mode=WAL;",
        "timeout": 20,
    },
}


def test_repo_defaults_pass():
    """
    The values from settings.py have to pass the check -- otherwise `manage.py check` would be red.

    This is also the only test that calls the *registered* function, so it checks that it goes
    through `settings.DATABASES` and does not reach into nothing.
    """
    assert check_sqlite_concurrency_options(app_configs=None) == []


def test_hardened_file_database_passes():
    assert problems_for("default", HARDENED) == []


def test_bare_file_database_is_flagged():
    """The case the check exists for: production sets DATABASES anew and leaves OPTIONS out."""
    problems = problems_for("default", {k: v for k, v in HARDENED.items() if k != "OPTIONS"})
    assert len(problems) == 1
    assert problems[0].id == "demockrazy.W001"
    # The message has to say *what* is missing -- otherwise it does not help.
    for expected in ("journal_mode", "timeout", "transaction_mode"):
        assert expected in problems[0].msg


def test_names_only_what_is_missing():
    config = dict(HARDENED, OPTIONS={"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"})
    problems = problems_for("default", config)
    assert len(problems) == 1
    assert "transaction_mode" in problems[0].msg
    assert "journal_mode" not in problems[0].msg
    assert "timeout" not in problems[0].msg


def test_in_memory_database_is_left_alone():
    """The test suite runs on :memory: -- there is no WAL and no concurrency there.

    Without this exception the check would complain about its own suite.
    """
    assert (
        problems_for("default", {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}) == []
    )


def test_other_backends_are_left_alone():
    """On Postgres (the `postgres` extra exists) none of this means anything."""
    config = {"ENGINE": "django.db.backends.postgresql", "NAME": "demockrazy"}
    assert problems_for("default", config) == []


def test_a_wrong_transaction_mode_is_flagged():
    """R9-1: any value used to be enough -- `DEFERRED` is the state 5.4 abolished.

    Measured with the defaults: 164 out of 200 concurrent votes then fail. A check that lets this
    through is exactly the silent failure it was built against (K1).
    """
    for value in ("DEFERRED", "EXCLUSIVE", "quatsch", ""):
        config = dict(HARDENED, OPTIONS=dict(HARDENED["OPTIONS"], transaction_mode=value))
        problems = problems_for("default", config)
        assert len(problems) == 1, value
        assert "transaction_mode" in problems[0].msg


def test_the_transaction_mode_may_be_written_in_any_case():
    """Django passes the value verbatim into a `BEGIN`, and SQLite is case-insensitive there."""
    config = dict(HARDENED, OPTIONS=dict(HARDENED["OPTIONS"], transaction_mode="immediate"))
    assert problems_for("default", config) == []


def test_a_timeout_of_zero_is_flagged():
    """R9-1: `"timeout" in options` was true for 0 as well -- so *no* waiting at all."""
    for value in (0, -1, None, "20"):
        config = dict(HARDENED, OPTIONS=dict(HARDENED["OPTIONS"], timeout=value))
        problems = problems_for("default", config)
        assert len(problems) == 1, value
        assert "timeout" in problems[0].msg


def test_a_journal_mode_other_than_wal_is_flagged():
    """The name alone is not enough: `journal_mode=DELETE` is the state before 5.4."""
    config = dict(
        HARDENED, OPTIONS=dict(HARDENED["OPTIONS"], init_command="PRAGMA journal_mode=DELETE;")
    )
    problems = problems_for("default", config)
    assert len(problems) == 1
    assert "journal_mode" in problems[0].msg
