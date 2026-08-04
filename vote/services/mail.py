"""Mailversand für die Umfrage-Erstellung.

Bis 3.4 steckte das als Satz geschachtelter Funktionen in `create()`. Herausgezogen, weil es keine
Request-Abhängigkeit hat, weil der Batch-Modus (Ziel 2) genau hier andockt, und weil keine Mail
rausgehen darf, bevor die Tokens durabel sind (B7) -- siehe notes/plan.md §11.

*(Hier stand „weil SMTP nicht in der Request-Transaktion laufen darf". Eine Request-Transaktion gab
es nie: das modulweite `ATOMIC_REQUESTS` hat Django nicht gelesen, B16. Der Befund bleibt, nur die
Begründung war falsch -- vorher verschickte `create()` die Mails **in der Save-Schleife**, während
die Tokens erst entstanden.)*

Die Texte stehen in `vote/templates/vote/mail/` und reproduzieren die früheren
`VOTE_*_MAIL_TEXT`-Settings **wortgleich**; `vote/tests/test_mail_service.py` nagelt das fest.
Autoescaping ist in den Templates abgeschaltet: es sind Plain-Text-Mails, ein `&` im
Umfragetitel soll nicht als `&amp;` beim Empfänger landen.
"""

import logging
from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def _absolute(path):
    """Macht aus einem Django-Pfad eine Adresse, die in eine Mail gehört."""
    return settings.VOTE_BASE_URL + path


def _render(name, context):
    """Betreff und Text aus zwei Templates. Der Betreff darf keinen Zeilenumbruch enthalten."""
    subject = render_to_string(f"vote/mail/{name}_subject.txt", context).strip()
    body = render_to_string(f"vote/mail/{name}_body.txt", context)
    return subject, body


def creator_message(poll, creator_mail, creator_token):
    """Die Mail an den Ersteller, mit Management-Link und Management-Token."""
    subject, body = _render(
        "creator",
        {
            "title": poll.title,
            "manage_url": _absolute(reverse("vote:polls:manage", args=(poll.identifier,))),
            "creator_token": creator_token,
        },
    )
    return (subject, body, creator_mail)


def voter_message(poll, voter_mail, token_string):
    """Die Einladung an einen Wähler, mit dem Abstimmungslink samt Token."""
    subject, body = _render(
        "voter",
        {
            "title": poll.title,
            "vote_base_url": settings.VOTE_BASE_URL,
            "poll_url_with_token": _absolute(poll.get_absolute_url()) + "?token=" + token_string,
        },
    )
    return (subject, body, voter_mail)


def deliver(messages):
    """Verschickt fertig gerenderte Nachrichten und schluckt Zustellfehler.

    Ein einzelner unerreichbarer Empfänger darf die übrigen nicht aufhalten. Die Fehler landen
    im Log und **nicht** mehr in der Antwort an den Ersteller: der Versand läuft nach dem Commit,
    die Seite ist da schon gerendert (B7).

    Absichtlich ohne Empfängeradresse und ohne Umfragekennung im Logaufruf -- die Zuordnung
    „Adresse gehört zu Umfrage X" wird bewusst nirgends persistiert (F8). Der Text einer
    SMTP-Exception kann die Adresse allerdings selbst enthalten; das ist mit F8 zu bewerten,
    wenn Ziel 2 einen echten Zustellbericht bekommt.
    """
    for subject, body, recipient in messages:
        try:
            if settings.VOTE_SEND_MAILS:
                send_mail(subject, body, settings.VOTE_MAIL_FROM, [recipient], fail_silently=False)
            else:
                # Wie bisher: bei abgeschaltetem Versand nur ausgeben, damit lokal sichtbar ist,
                # was rausgegangen wäre.
                print(subject, body, settings.VOTE_MAIL_FROM, [recipient])
        except SMTPException:
            logger.exception("Zustellung einer Umfrage-Mail fehlgeschlagen")
        except UnicodeEncodeError:
            logger.exception("Umfrage-Mail nicht kodierbar")


def poll_created_messages(poll, creator_mail, voter_mails, tokens):
    """Alle Mails einer neu erstellten Umfrage, in Versandreihenfolge: Ersteller, dann Wähler.

    Rendert vollständig vor, damit `deliver()` ohne Datenbankzugriff auskommt und als
    `on_commit`-Callback laufen kann.
    """
    messages = [creator_message(poll, creator_mail, poll.creator_token)]
    for voter_mail, token in zip(voter_mails, tokens, strict=True):
        messages.append(voter_message(poll, voter_mail, token.token_string))
    return messages
