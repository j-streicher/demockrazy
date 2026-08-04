"""Wie weit reicht eine Transaktion? (Plan B16)

Von 2016 bis 2026 stand in `demockrazy/settings.py` ein modulweites `ATOMIC_REQUESTS = True`.
Django liest die Option **pro Datenbank**, der Wert war also nie wirksam. Diese Tests halten den
tatsächlichen Zustand fest, damit ihn niemand wieder aus einem Kommentar erschließen muss.

Was die Atomarität stattdessen trägt, ist an seinen Stellen getestet und hier nicht wiederholt:
`vote/tests/test_poll_service.py::test_rolls_back_as_a_whole` für die Umfrage-Erstellung,
`vote/tests/test_views.py::test_incomplete_answer_rolls_everything_back` für die Stimmabgabe.
Beide waren grün, während diese Option nichts tat -- das ist der Beleg.
"""

from django.core.handlers.base import BaseHandler
from django.db import connections
from django.urls import resolve


def test_requests_are_not_wrapped_in_a_transaction():
    """Wird das hier rot, hat jemand `ATOMIC_REQUESTS` tatsächlich eingeschaltet.

    Das wäre kein Fehler, aber eine Entscheidung, die zu treffen ist statt einzusammeln: auf SQLite
    mit vier uwsgi-Prozessen nimmt dann jeder Request eine Transaktion, auch die reine
    Ergebnisseite (B13). Begründung und offene Frage F18 stehen in demockrazy/settings.py.
    """
    assert connections.settings["default"]["ATOMIC_REQUESTS"] is False


def test_django_wraps_no_view():
    """Die Gegenprobe zum Setting-Wert, einen Schritt näher am Verhalten.

    `make_view_atomic()` ist die Stelle, die die Option auswertet; sie gibt die View unverändert
    zurück, solange keine Transaktion um den Request gelegt wird. Ohne diesen Test wäre der obige
    nur eine Aussage über ein Dictionary.
    """
    handler = BaseHandler()
    for path in ("/vote/", "/vote/create"):
        view = resolve(path).func
        assert handler.make_view_atomic(view) is view, path
