"""Operational endpoints. Not part of voting, which is why they are not in `vote`."""

import logging

from django.db import connection, transaction
from django.http import HttpResponse
from django.views.decorators.http import require_safe

logger = logging.getLogger(__name__)


@transaction.non_atomic_requests
@require_safe
def healthz(request):
    """Says whether this process can serve requests **and** read the database.

    Why the database is included: without it the endpoint only answers "uwsgi is alive and the
    URLconf loads". What can go wrong with this particular deployment is then invisible -- the
    database is a SQLite file under `/var/lib/demockrazy` that the service reaches from the
    read-only Nix store. If the path is wrong after a deploy, or the file is not readable, every
    page returns a 500 while a plain 200 endpoint would report "healthy".

    **No write test.** What really matters for voting is writability -- but checking that would mean
    writing to the database on every request. With four uwsgi processes on one SQLite file (B13) the
    health check would then itself be a cause of the lock errors it is supposed to report.

    `non_atomic_requests` has no effect today -- there is no transaction around the request (B16,
    reasoning in settings.py). It is here anyway: if the option is ever switched on (F18), an
    endpoint polled every second that never writes is the first that should be exempt. Recorded in
    demockrazy/tests/test_healthz.py so the line does not disappear as decoration.
    """
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        # The endpoint is unauthenticated: the reason belongs in the log, not in the response.
        # The text of a database exception contains the file path.
        logger.exception("healthz: Datenbank nicht lesbar")
        return HttpResponse("database unavailable\n", status=503, content_type="text/plain")
    return HttpResponse("ok\n", content_type="text/plain")
