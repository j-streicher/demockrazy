"""System-Checks, die stille Fehlkonfiguration sichtbar machen.

Diese Datei existiert wegen einer Lehre aus zwei Befunden dieses Projekts: `ATOMIC_REQUESTS` war
zehn Jahre wirkungslos (B16) und `.gitignore` schluckte zehn Jahre die Frontend-Assets (B18). Beide
hatten dieselbe Eigenschaft -- **sie sahen richtig aus und taten nichts**, ohne dass irgendwo eine
Meldung erschien.

Die SQLite-Härtung aus 5.4 kann genauso enden: sie steht in `DATABASES['OPTIONS']`, und das
generierte `demockrazy_config` setzt `DATABASES` in Produktion komplett neu. Dieser Check macht das
Fehlen sichtbar, statt es dem nächsten `database is locked` zu überlassen.

Nach dem Deploy prüfbar mit:

    DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check
"""

from django.conf import settings
from django.core.checks import Warning, register

HINWEIS = (
    "Ohne transaction_mode='IMMEDIATE' liefert SQLite ein sofortiges SQLITE_BUSY, wenn eine "
    "Transaktion von Lesen auf Schreiben hochstufen muss -- der timeout greift dann nicht. Mit "
    "vier uwsgi-Prozessen auf einer Datei sind das die 'database is locked'-Fehler aus B13. "
    "Gemessen: 164 von 200 gleichzeitigen Stimmabgaben scheiterten daran. Die Werte stehen als "
    "Default in demockrazy/settings.py. Schlaegt dieser Check an, hat ein ueberschreibendes "
    "Settings-Modul DATABASES neu gesetzt und sie dabei verloren -- dann gehoeren sie dorthin (in "
    "Produktion: ins NixOS-Modul bzw. in dessen djangoSettings-Option)."
)


def _is_file_backed_sqlite(config):
    """SQLite auf einer Datei -- nur dort gibt es Sperren und nur dort wirkt WAL."""
    if "sqlite3" not in config.get("ENGINE", ""):
        return False
    name = str(config.get("NAME", ""))
    # In-Memory kennt kein WAL (`journal_mode` bleibt dort `memory`) und hat keine Nebenläufigkeit
    # zwischen Prozessen. Die Testsuite läuft so -- der Check darf sie nicht anmeckern.
    return name != ":memory:" and "mode=memory" not in name


def problems_for(alias, config):
    """Prüft *einen* `DATABASES`-Eintrag. Reine Funktion, damit sie ohne Settings testbar ist.

    Der Umweg ist Absicht: ein Test, der `settings.DATABASES` überschreibt, holt sich von Django
    ein `UserWarning` („can lead to unexpected behavior") -- zu Recht, denn die offenen
    Verbindungen hängen daran. Hier gibt es nichts zu überschreiben.
    """
    if not _is_file_backed_sqlite(config):
        return []

    options = config.get("OPTIONS") or {}
    fehlt = []
    if "journal_mode" not in str(options.get("init_command", "")).lower():
        fehlt.append("init_command mit 'PRAGMA journal_mode=WAL;'")
    if "timeout" not in options:
        fehlt.append("timeout (sqlite3-Default sind 5 s)")
    if not options.get("transaction_mode"):
        fehlt.append("transaction_mode='IMMEDIATE'")
    if not fehlt:
        return []

    return [
        Warning(
            f"DATABASES[{alias!r}] ist SQLite auf einer Datei, ohne die Härtung aus Plan 5.4. "
            f"Es fehlt: {', '.join(fehlt)}.",
            hint=HINWEIS,
            id="demockrazy.W001",
        )
    ]


@register()
def check_sqlite_concurrency_options(app_configs, **kwargs):
    """Meldet jede SQLite-Datenbank, der die Härtung aus Plan 5.4 fehlt.

    Absichtlich **ohne** `Tags.database`: so getaggte Checks lässt `manage.py check` ohne
    `--database` aus, und dann wäre der Check genau in dem Moment still, für den er gedacht ist.
    Er fragt nur die Settings ab und öffnet keine Verbindung.
    """
    problems = []
    for alias, config in settings.DATABASES.items():
        problems.extend(problems_for(alias, config))
    return problems
