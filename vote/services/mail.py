"""Mailversand für die Umfrage-Erstellung -- Rendern, Einreihen, getaktet Verschicken.

Bis 3.4 steckte das als Satz geschachtelter Funktionen in `create()`. Herausgezogen, weil es keine
Request-Abhängigkeit hat, weil der Batch-Modus (Ziel 2) genau hier andockt, und weil keine Mail
rausgehen darf, bevor die Tokens durabel sind (B7) -- siehe notes/plan.md §11.

*(Hier stand „weil SMTP nicht in der Request-Transaktion laufen darf". Eine Request-Transaktion gab
es nie: das modulweite `ATOMIC_REQUESTS` hat Django nicht gelesen, B16. Der Befund bleibt, nur die
Begründung war falsch -- vorher verschickte `create()` die Mails **in der Save-Schleife**, während
die Tokens erst entstanden.)*

**Seit dem getakteten Versand (Plan §11.7) gibt es hier zwei getrennte Hälften**, und die Trennung
ist Absicht -- sie ist die Form, die Djangos künftiges `django.tasks` auch hat (§11.7, 6a):

* **Einreihen** (`enqueue`) passiert im Request, in derselben Transaktion wie die Tokens.
* **Verschicken** (`send_pending`) passiert in einem anderen Prozess, aufgerufen vom
  Management-Command `send_pending_mails`. `deliver()` -- das alles sofort verschickte -- gibt es
  nicht mehr; es war die Stelle, die laut Plan §11.1 ein Batch-Versender ersetzt.

Die Texte stehen in `vote/templates/vote/mail/` und reproduzieren die früheren
`VOTE_*_MAIL_TEXT`-Settings **wortgleich**; `vote/tests/test_mail_service.py` nagelt das fest.
Autoescaping ist in den Templates abgeschaltet: es sind Plain-Text-Mails, ein `&` im
Umfragetitel soll nicht als `&amp;` beim Empfänger landen.
"""

import enum
import logging
import random
import time
from smtplib import SMTPException, SMTPRecipientsRefused, SMTPResponseException

from django.conf import settings
from django.core.mail import BadHeaderError, get_connection, send_mail
from django.template.loader import render_to_string
from django.urls import reverse

from ..models import OutgoingMail

logger = logging.getLogger(__name__)

#: Wie oft eine Nachricht abgelehnt werden darf, bevor sie aufgegeben wird. Gezählt werden **nur**
#: Absagen des Servers für genau diese Nachricht -- ein nicht erreichbarer Server kostet keinen
#: Versuch, sonst würde ein einstündiger Ausfall die Einladungen der Reihe nach wegwerfen.
#: Bei Minutentakt sind zehn Absagen derselben Nachricht zehn Minuten lang; wer so lange nur diese
#: eine Adresse ablehnt, lehnt sie ab und drosselt nicht.
MAX_ATTEMPTS = 10


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


class _Outcome(enum.Enum):
    """Was aus einem Versandversuch geworden ist. Danach entscheidet sich, was die Zeile erlebt."""

    SENT = "sent"
    #: Der Server hat *diese* Nachricht dauerhaft abgelehnt (5xx) oder sie ist nicht kodierbar.
    PERMANENT = "permanent"
    #: Der Server hat *diese* Nachricht vorläufig abgelehnt (4xx) -- der `450` der Drosselung.
    TRANSIENT = "transient"
    #: Der Server war nicht erreichbar oder ist weggebrochen. Kein Urteil über die Nachricht.
    UNREACHABLE = "unreachable"


def _smtp_code(error):
    """Der Antwortcode aus einer smtplib-Ausnahme, oder `None`, wenn es keinen gibt.

    Zwei Formen kommen vor: `SMTPResponseException` trägt `smtp_code` direkt,
    `SMTPRecipientsRefused` trägt pro Empfänger ein `(code, text)`-Paar. Hier steht genau ein
    Empfänger pro Nachricht, also ist es genau ein Code.
    """
    code = getattr(error, "smtp_code", None)
    if code is not None:
        return code
    refused = getattr(error, "recipients", None) or {}
    codes = [value[0] for value in refused.values() if value]
    return min(codes) if codes else None


def _send_one(connection, row):
    """Verschickt eine Zeile und sagt, was daraus geworden ist. Wirft nicht."""
    try:
        # `fail_silently=False` bleibt: die Ausnahme *ist* die Information. Sie greift, weil
        # `send_mail` mit übergebener `connection` deren `fail_silently` benutzt -- und
        # `get_connection()` steht auf False.
        send_mail(
            row.subject,
            row.body,
            settings.VOTE_MAIL_FROM,
            [row.recipient],
            fail_silently=False,
            connection=connection,
        )
    except (UnicodeEncodeError, BadHeaderError):
        # R5-1: eine Zeile, die sich **gar nicht** zu einer Nachricht bauen lässt, ist ein Fall für
        # sich -- sie wird von keinem Wiederholungsversuch besser. `BadHeaderError` erbt von
        # `ValueError`, nicht von `SMTPException`, und flog deshalb bis in den Command; weil die
        # Zeile vorn in der Warteschlange liegen bleibt, stand danach der Versand *aller* Umfragen.
        logger.exception("Umfrage-Mail lässt sich nicht als Nachricht aufbauen und wird verworfen")
        return _Outcome.PERMANENT
    except (SMTPResponseException, SMTPRecipientsRefused) as error:
        code = _smtp_code(error)
        if code is not None and 400 <= code < 500:
            return _Outcome.TRANSIENT
        # R6-1: der Code gehört ins Log, und zwar hier, wo er bekannt ist. Vorher stand die Meldung
        # ohne ihn im Aufrufer, und aus „eine Mail wurde abgelehnt" war nicht zu entscheiden, ob
        # eine Adresse falsch war oder der Server zickt. Ein Code ist eine Zahl, keine Adresse (F8).
        logger.warning("Eine Umfrage-Mail wurde mit SMTP-Code %s dauerhaft abgelehnt", code)
        return _Outcome.PERMANENT
    except (SMTPException, OSError):
        # Verbindung weg, DNS kaputt, Timeout. **Kein Urteil über die Nachricht** -- deshalb hier
        # auch kein `attempts`-Hochzählen, siehe MAX_ATTEMPTS.
        logger.exception("Mailserver nicht erreichbar, Versand abgebrochen")
        return _Outcome.UNREACHABLE
    return _Outcome.SENT


def enqueue(messages):
    """Reiht gerenderte Nachrichten in die Warteschlange ein.

    **Gehört in dieselbe Transaktion wie die Tokens** und ist deshalb absichtlich *kein*
    `on_commit`-Callback: liefe es danach, könnte ein Absturz dazwischen Tokens ohne Einladung
    hinterlassen -- Wähler, die ihren Token nie erfahren, und eine Umfrage, die nur der Ersteller
    noch schließen kann. Die Zusage von B7 („keine Mail, bevor die Tokens durabel sind") hält
    trotzdem, und zwar strukturell: verschickt wird in einem anderen Prozess, und der sieht nur
    committete Zeilen.
    """
    return OutgoingMail.objects.bulk_create(
        [
            OutgoingMail(subject=subject, body=body, recipient=recipient)
            for subject, body, recipient in messages
        ]
    )


def send_pending(*, batch_size=None, pause=None, sleep=time.sleep):
    """Verschickt die Warteschlange getaktet: `batch_size` Nachrichten, dann `pause` Sekunden.

    Vom Management-Command `send_pending_mails` aufgerufen, nie aus einem Request -- ein Lauf
    dauert Minuten. Gibt eine Zusammenfassung als dict zurück (`sent`, `given_up`, `deferred`,
    `batches`); der Command schreibt sie nach stdout.

    **Die eine Regel, an der alles hängt: kein `sleep` innerhalb einer Transaktion.** Gemessen
    (notes/plan.md §11.7, 4a): kurze Transaktion je Mail und `sleep` außerhalb kostet eine
    gleichzeitige Stimmabgabe 7--9 ms, **unabhängig davon, wie lange der Lauf dauert**. Eine
    Transaktion, die über die Pause reicht, lässt Stimmen erst Sekunden warten und dann verloren
    gehen, sobald der Lauf länger dauert als der `timeout` von 20 s -- gemessen 8 von 200. Deshalb
    steht hier nirgends ein `atomic()` um die Schleife, und `save()`/`delete()` je Zeile sind
    jeweils ihre eigene kurze Transaktion.

    **Verschicken, dann löschen** -- nicht umgekehrt. Stirbt der Prozess dazwischen, geht die Mail
    doppelt raus; sie trägt denselben einmaligen Token, eine doppelte Einladung ist also harmlos.
    Der umgekehrte Fehler *verliert* eine Einladung, und dann fehlt ein Token für immer: die
    Umfrage schließt nicht mehr von selbst.

    **Beim ersten vorläufigen Fehler bricht der Lauf ab**, statt die restlichen 29 gegen dieselbe
    Wand zu fahren. Ein `450` heißt „du bist über dem Limit"; der nächste Timer-Aufruf trifft ein
    zurückgesetztes Zeitfenster an. Ein *dauerhafter* Fehler (5xx) betrifft nur diese Adresse, dort
    läuft der Batch weiter.

    Eine **eigene Verbindung pro Batch**: die Pause soll nicht in einer offenen Verbindung
    verbracht werden, und die Batchgrenze ist der natürliche Ort dafür. Innerhalb eines Batches
    bleibt es bei einer Verbindung für 30 Nachrichten statt 30 Verbindungen.
    """
    batch_size = settings.VOTE_MAIL_BATCH_SIZE if batch_size is None else batch_size
    pause = settings.VOTE_MAIL_BATCH_PAUSE if pause is None else pause
    summary = {"sent": 0, "given_up": 0, "batches": 0}

    vorige_spitze = None
    while True:
        rows = list(OutgoingMail.objects.order_by("pk")[:batch_size])
        if not rows:
            return _finish(summary)
        if rows[0].pk == vorige_spitze:
            # Wächter (R5-2). Die Schleife endet sonst ausschließlich dadurch, dass jeder Ausgang
            # entweder die Zeile löscht oder abbricht -- ein fünfter Fall, der das nicht tut, dreht
            # sich für immer und hält dabei die `flock`, womit überhaupt keine Mail mehr rausgeht.
            # Dieselbe vorderste Zeile zweimal heißt: dieser Durchlauf hat nichts bewegt.
            logger.error(
                "Versand kommt nicht voran, Lauf abgebrochen -- %s Zeilen liegen noch",
                OutgoingMail.objects.count(),
            )
            return _finish(summary)
        vorige_spitze = rows[0].pk
        if summary["batches"]:
            # Die Pause liegt **zwischen** den Batches: nicht vor dem ersten (sonst wartet jeder
            # Lauf umsonst) und nicht nach dem letzten (sonst hält der Command die Sperre länger,
            # als er arbeitet).
            sleep(pause)
        summary["batches"] += 1
        if _send_batch(rows, summary):
            return _finish(summary)


def _finish(summary):
    """Was noch liegt, wird am Ende *gezaehlt* und nicht pro Zeile mitgebucht.

    Der erste Versuch buchte es pro Zeile und rechnete dabei kumulative Summen gegen die Groesse
    eines Batches -- das ergab falsche Zahlen, sobald es mehr als einen Batch gab.
    """
    summary["remaining"] = OutgoingMail.objects.count()
    return summary


def _send_batch(rows, summary):
    """Verschickt einen Batch. Liefert True, wenn der ganze Lauf abbrechen soll."""
    if not settings.VOTE_SEND_MAILS:
        # Wie `deliver()` früher: bei abgeschaltetem Versand nur ausgeben, damit lokal sichtbar
        # ist, was rausgegangen wäre. Die Zeilen verschwinden trotzdem, sonst liefe der Lauf
        # endlos über dieselbe Warteschlange.
        for row in rows:
            print(row.subject, row.body, settings.VOTE_MAIL_FROM, [row.recipient])
            row.delete()
            summary["sent"] += 1
        return False

    connection = get_connection()
    try:
        for row in rows:
            outcome = _send_one(connection, row)
            if outcome is _Outcome.SENT:
                row.delete()
                summary["sent"] += 1
            elif outcome is _Outcome.PERMANENT:
                # Gelogt hat `_send_one()` schon, dort ist der Grund bekannt (R6-1) -- **ohne**
                # Adresse und ohne Umfragekennung (F8). Der Text einer Ausnahme kann die Adresse
                # enthalten; wo `logger.exception` steht, ist das mit F8 bewertet und in Kauf
                # genommen.
                row.delete()
                summary["given_up"] += 1
            elif outcome is _Outcome.TRANSIENT:
                row.attempts += 1
                if row.attempts >= MAX_ATTEMPTS:
                    logger.warning(
                        "Eine Umfrage-Mail wurde %s mal vorläufig abgelehnt und aufgegeben",
                        row.attempts,
                    )
                    row.delete()
                    summary["given_up"] += 1
                else:
                    row.save(update_fields=["attempts"])
                return True
            else:
                # Unerreichbar: die Zeile bleibt unverändert liegen, **ohne** Versuch. Ein
                # einstündiger Ausfall soll die Einladungen nicht der Reihe nach wegwerfen.
                return True
    finally:
        try:
            connection.close()
        except (SMTPException, OSError):
            # `close()` kann beim QUIT werfen. Das darf den Lauf nicht beenden -- die Mails dieses
            # Batches sind raus und ihre Zeilen gelöscht.
            logger.exception("SMTP-Verbindung ließ sich nicht ordentlich schließen")
    return False


def poll_created_messages(poll, creator_mail, voter_mails, tokens):
    """Alle Mails einer neu erstellten Umfrage, in Versandreihenfolge: Ersteller, dann Wähler.

    Rendert vollständig vor: der Versand läuft später in einem anderen Prozess und liest dann nur
    noch die Warteschlange, ohne Poll und Tokens zu brauchen (Plan §11.7).

    **Die Paarung wird gemischt** (Review R1-2). `bulk_create` legt die Tokens in der Reihenfolge
    der eingegebenen Adressen an, die `id`s liefen also parallel zur Empfängerliste -- und die
    Liste überlebt den Versand nicht, die `id`s schon. Wer die Liste kennt und die Datenbank lesen
    kann, sah an den verbliebenen `id`s, *wer* noch nicht abgestimmt hat. Gemischt sagt die
    Reihenfolge nichts mehr. Die Stimme selbst war davon nie berührt, sie trägt keine Kennung.
    """
    tokens = list(tokens)
    random.SystemRandom().shuffle(tokens)
    messages = [creator_message(poll, creator_mail, poll.creator_token)]
    for voter_mail, token in zip(voter_mails, tokens, strict=True):
        messages.append(voter_message(poll, voter_mail, token.token_string))
    return messages
