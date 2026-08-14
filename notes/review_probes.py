"""Sonden des umfassenden Reviews (notes/review.md, Plan §14).

Nicht Teil der Testsuite -- liegt hier, weil jeder Befund in review.md eine Reproduktion
braucht (Regel 2) und zwei davon ohne Skript kaum nachzustellen sind: die Nebenläufigkeit
von R4-1 und die Mutationssonde hinter R10-1/R10-2/R10-3.

Aufruf (die Sonden brauchen zum Teil eine Datei-Datenbank mit der Prod-Härtung):

    pytest notes/review_probes.py -s -p no:randomly                       # R3/R5/R6/R7/R9/R11
    pytest notes/review_probes.py -s -p no:randomly --ds=probe_settings   # R4-1 (Threads)

Vorbild ist notes/baseline_probe.py: das Skript hat seine Arbeit getan und bleibt als Referenz.
"""


# ============================================================ probe_race.py

import threading

import pytest
from django.db import connections
from django.test import Client

from vote.models import Poll


def _cast(barrier, results, poll_identifier, token_string):
    client = Client()
    try:
        barrier.wait(timeout=10)
        try:
            response = client.post(
                f"/vote/{poll_identifier}/vote",
                {"token": token_string, "choice": results["choice_id"]},
            )
            results.setdefault("status", []).append(response.status_code)
        except Exception as error:  # noqa: BLE001
            results.setdefault("status", []).append(type(error).__name__)
    finally:
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_probe_double_click_same_token():
    doubled = 0
    rounds = 100
    for _ in range(rounds):
        poll = Poll.objects.create(title="race", question_text="q", num_tokens=1)
        choice = poll.choice_set.create(choice_text="a")
        token = poll.token_set.create()
        barrier = threading.Barrier(2)
        results = {"choice_id": choice.pk}
        threads = [
            threading.Thread(
                target=_cast, args=(barrier, results, poll.identifier, token.token_string)
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        choice.refresh_from_db()
        poll.refresh_from_db()
        if choice.votes > 1:
            doubled += 1
            print(
                f"DOPPELT: votes={choice.votes} tokens_left={poll.token_set.count()} "
                f"is_active={poll.is_active} statuscodes={results.get('status')}"
            )
    print(f"ERGEBNIS: {doubled} von {rounds} Runden mit zwei Stimmen aus einem Token")

# ============================================================ probe_perf.py

import pytest
from django.db import connection, reset_queries
from django.test import Client
from django.test.utils import CaptureQueriesContext

from vote.models import OutgoingMail, Poll
from vote.services import mail


def _count(client, path, method="get", data=None):
    with CaptureQueriesContext(connection) as ctx:
        response = getattr(client, method)(path, data or {})
    return response, len(ctx.captured_queries)


@pytest.mark.django_db
def test_probe_query_counts(client):
    from vote.services.polls import create_poll as svc

    poll, tokens = svc(
        title="q", poll_type="simple_choice", question_text="q", choices=["a", "b", "c"],
        num_tokens=50,
    )
    tokens = [t.token_string for t in tokens]
    reset_queries()
    for label, path in [
        ("index", "/vote/"),
        ("poll", f"/vote/{poll.identifier}/"),
        ("manage", f"/vote/{poll.identifier}/manage"),
    ]:
        response, queries = _count(client, path)
        print(f"{label:8s} status={response.status_code} queries={queries}")
    response, queries = _count(
        client,
        f"/vote/{poll.identifier}/vote",
        "post",
        {"token": tokens[0], "choice": poll.choice_set.first().pk},
    )
    print(f"vote     status={response.status_code} queries={queries}")
    poll.is_active = False
    poll.save()
    response, queries = _count(client, f"/vote/{poll.identifier}/results")
    print(f"results  status={response.status_code} queries={queries}")


@pytest.mark.django_db
def test_probe_multiple_choice_vote_queries(client):
    from vote.services.polls import create_poll as svc

    poll, tokens = svc(
        title="m", poll_type="multiple_choice", question_text="q",
        choices=list("abcdefghij"), num_tokens=2,
    )
    payload = {"token": tokens[0].token_string}
    for choice in poll.choice_set.all():
        payload[f"choice{choice.id}"] = "yes"
    response, queries = _count(client, f"/vote/{poll.identifier}/vote", "post", payload)
    print(f"vote(multiple, 10 choices) status={response.status_code} queries={queries}")


@pytest.mark.django_db
def test_probe_create_queries_scale(client):
    for recipients in (1, 50, 150):
        with CaptureQueriesContext(connection) as ctx:
            response = client.post(
                "/vote/create",
                {
                    "title": f"t{recipients}",
                    "type": "simple_choice",
                    "description": "d",
                    "choices": "a\nb",
                    "creator_mail": "c@example.org",
                    "voter_mails": "\n".join(f"v{i}@example.org" for i in range(recipients)),
                },
            )
        print(
            f"create({recipients:3d} Empfänger) status={response.status_code} "
            f"queries={len(ctx.captured_queries)} queue={OutgoingMail.objects.count()}"
        )
        OutgoingMail.objects.all().delete()


@pytest.mark.django_db
def test_probe_caps(client):
    """R7: was ist außer der Empfängerzahl begrenzt?"""
    big_text = "x" * 200_000
    response = client.post(
        "/vote/create",
        {
            "title": "t",
            "type": "simple_choice",
            "description": big_text,
            "choices": "\n".join(f"c{i}" for i in range(5000)),
            "creator_mail": "c@example.org",
            "voter_mails": "v@example.org",
        },
    )
    poll = Poll.objects.filter(title="t").first()
    print("STATUS:", response.status_code)
    print("description gespeichert:", len(poll.question_text) if poll else None)
    print("choices gespeichert:", poll.choice_set.count() if poll else None)
    if poll:
        page, queries = _count(client, f"/vote/{poll.identifier}/")
        print(f"poll-Seite mit 5000 Choices: status={page.status_code} queries={queries} "
              f"bytes={len(page.content)}")
        body = OutgoingMail.objects.first().body
        print("Mailtext-Laenge:", len(body))


@pytest.mark.django_db
def test_probe_queue_row_content():
    """R1/R6: was steht in einer Warteschlangenzeile wirklich?"""
    from vote.services.polls import create_poll as svc

    poll, tokens = svc(
        title="Geheim", poll_type="simple_choice", question_text="q", choices=["a"], num_tokens=1
    )
    mail.enqueue(mail.poll_created_messages(poll, "creator@example.org", ["wähler@example.org"], tokens))
    for row in OutgoingMail.objects.all():
        print("---")
        print("recipient:", row.recipient)
        print("subject  :", row.subject)
        print("body     :", row.body.replace("\n", " | ")[:300])
    print("Identifier der Umfrage:", poll.identifier)
    print("Token:", tokens[0].token_string[:20], "...")

# ============================================================ probe_sec.py

import logging

import pytest
from django.contrib.sessions.models import Session
from django.test import Client

from vote.models import OutgoingMail, Poll


@pytest.mark.django_db
def test_probe_admin_surface(client):
    for path in ("/admin/", "/admin/vote/token/", "/admin/vote/poll/", "/admin/login/"):
        response = client.get(path)
        print(f"{path:24s} -> {response.status_code} {response.headers.get('Location', '')}")


@pytest.mark.django_db
def test_probe_admin_shows_tokens(admin_client):
    """Was sieht ein Staff-Account? (Der `admin_client` legt einen Superuser an.)"""
    poll = Poll.objects.create(title="Geheim", question_text="q", num_tokens=1)
    token = poll.token_set.create()
    page = admin_client.get("/admin/vote/token/").content.decode()
    print("Token-Liste zeigt token_string:", token.token_string[:12] in page)
    detail = admin_client.get(f"/admin/vote/poll/{poll.pk}/change/").content.decode()
    print("Poll-Detail zeigt creator_token:", poll.creator_token[:12] in detail)
    print("Poll-Detail zeigt identifier:", poll.identifier[:12] in detail)


@pytest.mark.django_db
def test_probe_headers(client):
    poll = Poll.objects.create(title="h", question_text="q", num_tokens=1)
    response = client.get(f"/vote/{poll.identifier}/")
    for name in (
        "X-Frame-Options",
        "Referrer-Policy",
        "X-Content-Type-Options",
        "Content-Security-Policy",
        "Cross-Origin-Opener-Policy",
        "Vary",
        "Cache-Control",
    ):
        print(f"{name:28s}: {response.headers.get(name, '-- fehlt --')}")


@pytest.mark.django_db
def test_probe_no_sessions_for_voters(client, create_poll=None):
    poll = Poll.objects.create(title="s", question_text="q", num_tokens=1)
    choice = poll.choice_set.create(choice_text="a")
    token = poll.token_set.create()
    client.get(f"/vote/{poll.identifier}/", {"token": token.token_string})
    client.post(
        f"/vote/{poll.identifier}/vote", {"token": token.token_string, "choice": choice.pk}
    )
    print("Session-Zeilen nach einer Stimmabgabe:", Session.objects.count())
    print("Cookies des Clients:", sorted(client.cookies.keys()))


@pytest.mark.django_db
def test_probe_log_lines_on_permanent_failure(caplog, settings, monkeypatch):
    """R6: welche Zeile landet im Log, wenn eine Mail dauerhaft abgelehnt wird?"""
    from smtplib import SMTPRecipientsRefused

    from vote.services import mail as mailservice

    OutgoingMail.objects.create(recipient="geheim@example.org", subject="s", body="b")

    class Boom:
        def __init__(self, *a, **k):
            pass

        def send_messages(self, messages):
            raise SMTPRecipientsRefused({"geheim@example.org": (550, b"unknown user")})

        def close(self):
            pass

    monkeypatch.setattr("vote.services.mail.get_connection", lambda *a, **k: Boom())
    with caplog.at_level(logging.DEBUG):
        print("SUMMARY:", mailservice.send_pending(pause=0))
    for record in caplog.records:
        print(f"[{record.levelname}] {record.name}: {record.getMessage()}")
        if record.exc_info:
            print("   exc:", repr(record.exc_info[1]))


@pytest.mark.django_db
def test_probe_healthz_body():
    from unittest.mock import patch

    client = Client()
    print("ok:", client.get("/healthz").status_code, client.get("/healthz").content)
    with patch("django.db.connection.cursor", side_effect=RuntimeError("db kaputt: /var/lib/x")):
        response = client.get("/healthz")
        print("kaputt:", response.status_code, response.content)
    print("POST /healthz:", client.post("/healthz").status_code)

# ============================================================ probe_inject2.py
import pytest
from vote.models import Poll


@pytest.mark.django_db
@pytest.mark.parametrize("payload,label", [
    ("a\r\nSet-Cookie: admin=1", "CRLF"),
    ("äöü", "Latin-1"),
    ("✓", "U+2713"),
    ("x" * 8000, "8000 Zeichen"),
])
def test_probe_setcookie_header(client, payload, label):
    poll = Poll.objects.create(title="t", question_text="q", num_tokens=1)
    response = client.get(f"/vote/{poll.identifier}/", {"token": payload})
    print(f"\n[{label}] status={response.status_code}")
    header = str(response.cookies["vote_token"])
    print("   Set-Cookie (repr):", repr(header[:120]))
    print("   Zeilenumbruch im Header:", "\r" in header or "\n" in header)
    try:
        raw = response.serialize_headers()
        print("   serialize_headers: OK,", len(raw), "Bytes")
    except Exception as error:
        print("   serialize_headers: RAISED", type(error).__name__, error)
    try:
        header.encode("latin-1")
        print("   latin-1-kodierbar (WSGI-Anforderung): ja")
    except UnicodeEncodeError as error:
        print("   latin-1-kodierbar (WSGI-Anforderung): NEIN ->", error)

# ============================================================ probe_order.py
import re
import pytest
from vote.models import OutgoingMail, Poll, Token


@pytest.mark.django_db
def test_probe_token_order_matches_recipient_order(client):
    voters = [f"{name}@example.org" for name in ("anna", "bert", "cara", "dora", "emil")]
    client.post("/vote/create", {
        "title": "Reihenfolge", "type": "simple_choice", "description": "d",
        "choices": "ja\nnein", "creator_mail": "chef@example.org",
        "voter_mails": "\n".join(voters),
    })
    poll = Poll.objects.get(title="Reihenfolge")
    tokens = list(Token.objects.filter(poll=poll).order_by("pk"))
    print("Tokens nach pk:", [t.pk for t in tokens])
    queue = list(OutgoingMail.objects.order_by("pk"))
    print("Warteschlange nach pk:", [(row.pk, row.recipient) for row in queue])
    paarung = []
    for row in queue:
        match = re.search(r"\?token=([A-Za-z0-9]+)", row.body)
        if match:
            token = Token.objects.get(token_string=match.group(1))
            paarung.append((row.recipient.split("@")[0], token.pk))
    print("Adresse -> Token-pk:", paarung)
    print("Token-pks aufsteigend in Eingabereihenfolge:",
          [p[1] for p in paarung] == sorted(p[1] for p in paarung))
    # Nach der Zustellung: Warteschlange leer, Tokens bleiben.
    OutgoingMail.objects.all().delete()
    print("nach Zustellung -- Adressen in der DB:",
          OutgoingMail.objects.count(), "| Tokens:", Token.objects.filter(poll=poll).count())
    # Zwei Wähler stimmen ab (der zweite und der vierte der Liste).
    for index in (1, 3):
        client.post(f"/vote/{poll.identifier}/vote",
                    {"token": paarung[index][1] and Token.objects.get(pk=paarung[index][1]).token_string,
                     "choice": poll.choice_set.first().pk})
    print("verbleibende Token-pks:", sorted(t.pk for t in Token.objects.filter(poll=poll)))
    print("fehlende pks verraten die Listenpositionen:", sorted(p[1] for p in paarung))

# ============================================================ probe_misc.py
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from vote.services.polls import create_poll


@pytest.mark.django_db
def test_probe_create_poll_statements():
    for n in (2, 200):
        with CaptureQueriesContext(connection) as ctx:
            create_poll(title=f"t{n}", poll_type="simple_choice", question_text="q",
                        choices=["a", "b"], num_tokens=n)
        print(f"create_poll({n} Tokens): {len(ctx.captured_queries)} Statements")
        for q in ctx.captured_queries:
            print("   ", q["sql"][:80])


# ============================================================ probe_settings.py
# Für die Threads-Sonde (R4-1) gebraucht: Testsettings auf einer *Datei* und mit der Prod-Härtung
# aus 5.4 -- :memory: kennt keine Sperren zwischen Verbindungen. Als probe_settings.py im
# Projektwurzel-Verzeichnis ablegen und mit --ds=probe_settings fahren.
#
#     import tempfile
#     from pathlib import Path
#
#     from demockrazy.test_settings import *  # noqa: F403
#
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": str(Path(tempfile.gettempdir()) / "demockrazy-probe.sqlite3"),
#             "OPTIONS": {
#                 "transaction_mode": "IMMEDIATE",
#                 "init_command": "PRAGMA journal_mode=WAL;",
#                 "timeout": 20,
#             },
#         }
#     }

# ============================================================ Mutationssonde (R10)
# Kein Skript hier, weil es Produktivdateien verändert -- das Verfahren in drei Sätzen, damit es
# nachvollziehbar bleibt: pro Mutation eine Textersetzung an genau einer Stelle, `pytest -q` mit
# `timeout 90` (eine Mutation lief in eine Endlosschleife, siehe R5-2), Datei aus einer Kopie
# zurückspielen. 26 Mutationen gefahren, 21 bemerkt. Die fünf unbemerkten:
#
#   @vary_on_cookie aus vote/views.py entfernt            -> 215 passed  (R10-1)
#   random.SystemRandom().choice -> random.choice          -> 215 passed  (R10-2)
#   VOTE_MAIL_BATCH_SIZE-Default 30 -> 1000                -> 215 passed  (R10-3)
#   DATABASES OPTIONS transaction_mode/journal_mode weg    -> 215 passed  (R9-2)
#   Enthaltungen auch bei multiple_choice anhängen         -> 215 passed  (R10-3)
#
# Bemerkt wurden u. a.: token.delete() entfernt (7 failed), atomic() in vote() entfernt,
# httponly/samesite geändert, Token-Länge 128->64, Adress-Dedup aus, Empfänger-Deckel aus,
# Pause zwischen Batches entfernt, MAX_ATTEMPTS 10->1, 4xx wie 5xx, EMAIL_TIMEOUT None,
# flock entfernt, creator_token-Vergleich immer wahr, beide is_active-Weichen, zip(strict=False),
# Choices-Reihenfolge umgedreht, mails_pending immer False, Converter auf Slug-Zeichen gelockert,
# Mail-Autoescaping an, Warteschlange in zufälliger Reihenfolge.
