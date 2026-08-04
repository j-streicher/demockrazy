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
from django.core.mail import get_connection, send_mail
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
    """Verschickt fertig gerenderte Nachrichten über **eine** SMTP-Verbindung und schluckt Fehler.

    Ein einzelner unerreichbarer Empfänger darf die übrigen nicht aufhalten. Die Fehler landen
    im Log und **nicht** mehr in der Antwort an den Ersteller: der Versand läuft nach dem Commit,
    die Seite ist da schon gerendert (B7).

    Absichtlich ohne Empfängeradresse und ohne Umfragekennung im Logaufruf -- die Zuordnung
    „Adresse gehört zu Umfrage X" wird bewusst nirgends persistiert (F8). Der Text einer
    SMTP-Exception kann die Adresse allerdings selbst enthalten; das ist mit F8 zu bewerten,
    wenn Ziel 2 einen echten Zustellbericht bekommt.

    **Die gemeinsame Verbindung ist der erste Schritt zu Ziel 2 und ausdrücklich nicht die Kur.**
    Vorher baute jeder `send_mail()`-Aufruf seine eigene Verbindung auf: gemessen 101 Nachrichten
    in **101** Verbindungen, jede mit TCP, STARTTLS und AUTH. Was das *nicht* behebt, ist die
    Drosselung des Mailservers: der zählt **Nachrichten** pro Zeitfenster
    (`450 4.7.1 too much mail from`, siehe notes/plan.md §11), und deren Zahl bleibt gleich.
    Schneller wird es trotzdem deutlich, und weil der Versand heute synchron im Request läuft,
    wartet genau so lange der Ersteller vor seinem Browser. **Die Kur ist Taktung plus
    Wiederholung der 450er, und die braucht den Weg aus dem Request heraus.**

    Zwei Feinheiten, die man beim Lesen nicht sieht:

    * Die Verbindung wird **nicht** vorab geöffnet. Djangos Backend öffnet sie beim ersten
      Versand selbst und hält sie danach -- ein fehlgeschlagener Aufbau bleibt damit ein Fehler
      *dieser* Nachricht, und die nächste versucht es erneut. Mit einem eigenen `open()` samt
      vorzeitigem Abbruch wäre ein kurzer Ausfall beim ersten Empfänger das Ende des ganzen
      Versands.
    * `close()` steht in einem eigenen `try`, weil es beim `QUIT` selbst eine `SMTPException`
      werfen kann. Sie darf hier nicht heraus: `deliver()` läuft als `on_commit`-Callback im
      Request, die Umfrage ist zu diesem Zeitpunkt schon angelegt, und ein Fehler daraus wäre ein
      500 auf einer Seite, die inhaltlich in Ordnung ist.
    """
    if not settings.VOTE_SEND_MAILS:
        # Wie bisher: bei abgeschaltetem Versand nur ausgeben, damit lokal sichtbar ist, was
        # rausgegangen wäre. Ohne Verbindung -- es gibt nichts zu verbinden.
        for subject, body, recipient in messages:
            print(subject, body, settings.VOTE_MAIL_FROM, [recipient])
        return

    connection = get_connection()
    try:
        for subject, body, recipient in messages:
            try:
                # `fail_silently=False` bleibt: die Ausnahme ist das, was hier protokolliert
                # wird. Sie greift, weil `send_mail` mit übergebener `connection` deren
                # `fail_silently` benutzt -- und `get_connection()` steht auf False.
                send_mail(
                    subject,
                    body,
                    settings.VOTE_MAIL_FROM,
                    [recipient],
                    fail_silently=False,
                    connection=connection,
                )
            except SMTPException:
                logger.exception("Zustellung einer Umfrage-Mail fehlgeschlagen")
            except UnicodeEncodeError:
                logger.exception("Umfrage-Mail nicht kodierbar")
    finally:
        try:
            connection.close()
        except SMTPException:
            logger.exception("SMTP-Verbindung ließ sich nicht ordentlich schließen")


def poll_created_messages(poll, creator_mail, voter_mails, tokens):
    """Alle Mails einer neu erstellten Umfrage, in Versandreihenfolge: Ersteller, dann Wähler.

    Rendert vollständig vor, damit `deliver()` ohne Datenbankzugriff auskommt und als
    `on_commit`-Callback laufen kann.
    """
    messages = [creator_message(poll, creator_mail, poll.creator_token)]
    for voter_mail, token in zip(voter_mails, tokens, strict=True):
        messages.append(voter_message(poll, voter_mail, token.token_string))
    return messages
