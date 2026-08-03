"""Phase 0.2 – Baseline-Verhalten des Ist-Stands protokollieren.

Laeuft gegen eine temporaere Test-DB, faesst die Dev-DB nicht an.
Ausgabe ist bewusst ein Protokoll, kein Assert-Lauf: es geht darum
festzuhalten, was der Code HEUTE tut (inkl. der Bugs).
"""
import os
import sys

sys.path.insert(0, "/home/julien/Desktop/wahlcomputer-update/demockrazy")
os.environ["DJANGO_SETTINGS_MODULE"] = "demockrazy.settings"

import django
from django.test.utils import setup_test_environment

setup_test_environment()
django.setup()

from django.db import connection
from django.conf import settings

settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
settings.VOTE_SEND_MAILS = True  # damit die Mails in locmem landen und inspizierbar sind
settings.ALLOWED_HOSTS = ["testserver"]

connection.creation.create_test_db(verbosity=0)

from django.core import mail
from django.test import Client

from vote.models import Poll, Choice, Token

results = []


def probe(name, fn):
    try:
        out = fn()
        results.append((name, "OK", out))
    except Exception as exc:
        results.append((name, type(exc).__name__, str(exc).splitlines()[0][:160]))


c = Client()

# ---------------------------------------------------------------- 1. Index
probe("GET /vote/ (index)", lambda: c.get("/vote/").status_code)

# ---------------------------------------------------------------- 2. B3: create via GET
probe("GET /vote/create (B3 erwartet Crash)", lambda: c.get("/vote/create").status_code)

# ---------------------------------------------------------------- 3. Happy path: simple_choice
def create_simple():
    mail.outbox.clear()
    r = c.post(
        "/vote/create",
        {
            "title": "Baseline Simple",
            "type": "simple_choice",
            "description": "Frage?",
            "choices": "Ja\nNein\n\n  Vielleicht  \n",
            "creator_mail": "admin@example.org",
            "voter_mails": "a@example.org\nb@example.org\n",
        },
    )
    p = Poll.objects.get(title="Baseline Simple")
    return {
        "status": r.status_code,
        "choices": list(p.choice_set.values_list("choice_text", flat=True)),
        "num_tokens": p.num_tokens,
        "tokens_in_db": p.token_set.count(),
        "mails_sent": len(mail.outbox),
        "mail_subjects": [m.subject for m in mail.outbox],
        "mail_to": [m.to for m in mail.outbox],
        "identifier_len": len(p.identifier),
        "creator_token_len": len(p.creator_token),
        "amount_used_unused": p.get_amount_used_unused(),
    }


probe("POST /vote/create simple_choice", create_simple)

poll = Poll.objects.filter(title="Baseline Simple").first()

# ---------------------------------------------------------------- 4. Token aus der Mail ziehen
def token_from_mail():
    voter_mails = [m for m in mail.outbox if m.to != ["admin@example.org"]]
    body = voter_mails[0].body
    tok = body.split("?token=")[1].split()[0]
    return {"token_prefix": tok[:12] + "...", "token_len": len(tok), "in_db": Token.objects.filter(token_string=tok).exists()}


probe("Token aus Wähler-Mail extrahierbar", token_from_mail)


def get_tokens():
    return [m.body.split("?token=")[1].split()[0] for m in mail.outbox if m.to != ["admin@example.org"]]


tokens = get_tokens()

# ---------------------------------------------------------------- 5. Poll-Seite mit Token
probe(
    "GET /vote/<id>/?token=... ",
    lambda: c.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}).status_code,
)
probe(
    "GET /vote/<id>/?token=falsch (Fehlermeldung erwartet)",
    lambda: c.get(f"/vote/{poll.identifier}/", {"token": "nope"}).context["error_message"],
)

# ---------------------------------------------------------------- 6. Abstimmen
def do_vote():
    choice = poll.choice_set.first()
    r = c.post(f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.id})
    choice.refresh_from_db()
    return {
        "status": r.status_code,
        "redirect": r.headers.get("Location"),
        "votes": choice.votes,
        "token_geloescht": not Token.objects.filter(token_string=tokens[0]).exists(),
        "poll_active": Poll.objects.get(pk=poll.pk).is_active,
    }


probe("POST vote (1 von 2 Tokens)", do_vote)

# ---------------------------------------------------------------- 7. B2: POST vote ohne token
probe(
    "POST vote ohne 'token' (B2 erwartet UnboundLocalError)",
    lambda: c.post(f"/vote/{poll.identifier}/vote", {"choice": poll.choice_set.first().id}).status_code,
)

# ---------------------------------------------------------------- 8. Abstimmen ohne Auswahl
probe(
    "POST vote ohne 'choice'",
    lambda: c.post(f"/vote/{poll.identifier}/vote", {"token": tokens[1]}).context["error_message"],
)

# ---------------------------------------------------------------- 9. Letzter Token -> Auto-Close
def last_vote():
    choice = poll.choice_set.last()
    r = c.post(f"/vote/{poll.identifier}/vote", {"token": tokens[1], "choice": choice.id})
    p = Poll.objects.get(pk=poll.pk)
    return {
        "status": r.status_code,
        "poll_active": p.is_active,
        "tokens_remaining": p.token_set.count(),
        "amount_used_unused": p.get_amount_used_unused(),
    }


probe("POST vote (letzter Token -> Auto-Close)", last_vote)

# ---------------------------------------------------------------- 10. Ergebnisse
probe("GET /vote/<id>/results nach Close", lambda: c.get(f"/vote/{poll.identifier}/results").status_code)
probe(
    "GET /vote/<id>/ nach Close (Redirect auf results erwartet)",
    lambda: (c.get(f"/vote/{poll.identifier}/").status_code, c.get(f"/vote/{poll.identifier}/").headers.get("Location")),
)

# ---------------------------------------------------------------- 11. Doppelte Mailadressen (B6)
def duplicate_mails():
    mail.outbox.clear()
    c.post(
        "/vote/create",
        {
            "title": "Baseline Duplikate",
            "type": "simple_choice",
            "description": "?",
            "choices": "Ja\nNein",
            "creator_mail": "admin@example.org",
            "voter_mails": "dup@example.org\ndup@example.org\ndup@example.org\n",
        },
    )
    p = Poll.objects.get(title="Baseline Duplikate")
    voter = [m for m in mail.outbox if m.to == ["dup@example.org"]]
    return {"num_tokens": p.num_tokens, "tokens": p.token_set.count(), "mails_an_dup": len(voter)}


probe("POST create mit 3x derselben Adresse (B6)", duplicate_mails)

# ---------------------------------------------------------------- 12. Ungueltige Mailadresse
probe(
    "POST create mit kaputter Mailadresse",
    lambda: c.post(
        "/vote/create",
        {
            "title": "Baseline Kaputt",
            "type": "simple_choice",
            "description": "?",
            "choices": "Ja",
            "creator_mail": "admin@example.org",
            "voter_mails": "keinemail",
        },
    ).status_code,
)

# ---------------------------------------------------------------- 13. Ungueltiger Poll-Typ
probe(
    "POST create mit type=quatsch",
    lambda: c.post(
        "/vote/create",
        {
            "title": "Baseline Typ",
            "type": "quatsch",
            "description": "?",
            "choices": "Ja",
            "creator_mail": "admin@example.org",
            "voter_mails": "a@example.org",
        },
    ).status_code,
)

# ---------------------------------------------------------------- 14. multiple_choice
def multiple_choice_flow():
    mail.outbox.clear()
    c.post(
        "/vote/create",
        {
            "title": "Baseline Multi",
            "type": "multiple_choice",
            "description": "?",
            "choices": "A\nB\nC",
            "creator_mail": "admin@example.org",
            "voter_mails": "m@example.org",
        },
    )
    p = Poll.objects.get(title="Baseline Multi")
    tok = [m.body.split("?token=")[1].split()[0] for m in mail.outbox if m.to == ["m@example.org"]][0]
    ch = list(p.choice_set.all())
    data = {"token": tok, f"choice{ch[0].id}": "yes", f"choice{ch[1].id}": "no", f"choice{ch[2].id}": "yes"}
    r = c.post(f"/vote/{p.identifier}/vote", data)
    p.refresh_from_db()
    return {
        "status": r.status_code,
        "votes": {x.choice_text: Choice.objects.get(pk=x.pk).votes for x in ch},
        "poll_active": p.is_active,
        "amount_used_unused": p.get_amount_used_unused(),
    }


probe("multiple_choice: 2x yes, 1x no", multiple_choice_flow)

# ---------------------------------------------------------------- 15. multiple_choice mit unvollstaendigem POST
def multiple_incomplete():
    mail.outbox.clear()
    c.post(
        "/vote/create",
        {
            "title": "Baseline Multi Teil",
            "type": "multiple_choice",
            "description": "?",
            "choices": "A\nB",
            "creator_mail": "admin@example.org",
            "voter_mails": "m2@example.org",
        },
    )
    p = Poll.objects.get(title="Baseline Multi Teil")
    tok = [m.body.split("?token=")[1].split()[0] for m in mail.outbox if m.to == ["m2@example.org"]][0]
    ch = list(p.choice_set.all())
    r = c.post(f"/vote/{p.identifier}/vote", {"token": tok, f"choice{ch[0].id}": "yes"})
    return {
        "status": r.status_code,
        "error": r.context["error_message"] if r.status_code == 200 and r.context else None,
        "votes": [Choice.objects.get(pk=x.pk).votes for x in ch],
        "token_noch_da": Token.objects.filter(token_string=tok).exists(),
    }


probe("multiple_choice mit nur 1 von 2 Antworten", multiple_incomplete)

# ---------------------------------------------------------------- 16. manage
def manage_flow():
    mail.outbox.clear()
    c.post(
        "/vote/create",
        {
            "title": "Baseline Manage",
            "type": "simple_choice",
            "description": "?",
            "choices": "Ja\nNein",
            "creator_mail": "admin@example.org",
            "voter_mails": "x@example.org\ny@example.org",
        },
    )
    p = Poll.objects.get(title="Baseline Manage")
    falsch = c.post(f"/vote/{p.identifier}/manage", {"token": "falsch"})
    richtig = c.post(f"/vote/{p.identifier}/manage", {"token": p.creator_token})
    p.refresh_from_db()
    return {
        "falscher_token": falsch.context["error_message"],
        "richtiger_token_status": richtig.status_code,
        "redirect": richtig.headers.get("Location"),
        "poll_active": p.is_active,
        "amount_used_unused_nach_close": p.get_amount_used_unused(),
    }


probe("manage: Poll vorzeitig schliessen", manage_flow)

probe("GET /vote/<id>/manage ohne token-Feld im POST", lambda: c.post("/vote/%s/manage" % Poll.objects.get(title="Baseline Duplikate").identifier, {}).status_code)

# ---------------------------------------------------------------- 17. num_tokens=None Pfad
def num_tokens_none():
    p = Poll.objects.create(title="Baseline None", question_text="?", num_tokens=None)
    Choice.objects.create(poll=p, choice_text="A", votes=3)
    Token.objects.create(poll=p)
    return p.get_amount_used_unused()


probe("get_amount_used_unused mit num_tokens=None", num_tokens_none)

# ---------------------------------------------------------------- 18. Root-Redirect
probe("GET / (Redirect)", lambda: (c.get("/").status_code, c.get("/").headers.get("Location")))

# ---------------------------------------------------------------- Ausgabe
print()
print("=" * 100)
print("PHASE 0.2 – BASELINE-PROTOKOLL (Django %s)" % django.get_version())
print("=" * 100)
for name, kind, out in results:
    print("\n[%-18s] %s" % (kind, name))
    print("    -> %r" % (out,))
