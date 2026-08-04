"""Betriebs-Endpunkte. Gehören nicht zur Abstimmung und liegen deshalb nicht in `vote`."""

import logging

from django.db import connection, transaction
from django.http import HttpResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@transaction.non_atomic_requests
@require_safe
def healthz(request):
    """Sagt, ob dieser Prozess Requests bedienen **und** die Datenbank lesen kann.

    Warum die Datenbank mitgeprüft wird: ohne sie beantwortet der Endpunkt nur „uwsgi lebt und die
    URLconf lädt". Was an genau diesem Deployment schiefgehen kann, sieht man dann nicht -- die
    Datenbank ist eine SQLite-Datei unter `/var/lib/demockrazy`, auf die der Dienst aus dem
    read-only Nix-Store zugreift. Steht der Pfad nach einem Deploy falsch oder ist die Datei nicht
    lesbar, liefert jede Seite einen 500, während ein reiner 200-Endpunkt „gesund" meldete.

    **Kein Schreibtest.** Was für die Stimmabgabe wirklich zählt, ist Schreibbarkeit -- die zu
    prüfen hieße aber, bei jedem Aufruf in die Datenbank zu schreiben. Bei vier uwsgi-Prozessen auf
    einer SQLite-Datei (B13) wäre der Health-Check damit selbst eine Ursache der Lock-Fehler, die er
    melden soll.

    `non_atomic_requests` ist heute wirkungslos -- es gibt keine Transaktion um den Request (B16,
    Begründung in settings.py). Es steht trotzdem da: wird die Option je eingeschaltet (F18), ist
    ein im Sekundentakt gepollter Endpunkt, der nie schreibt, der erste, der davon ausgenommen
    gehört. Festgehalten in demockrazy/tests/test_healthz.py, damit die Zeile nicht als Zierrat
    verschwindet.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        # Der Endpunkt ist unauthentifiziert: der Grund gehört ins Log, nicht in die Antwort.
        # Der Text einer Datenbank-Exception enthält den Dateipfad.
        logger.exception("healthz: Datenbank nicht lesbar")
        return HttpResponse("database unavailable\n", status=503, content_type="text/plain")
    return HttpResponse("ok\n", content_type="text/plain")
