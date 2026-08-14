"""Mail for poll creation -- rendering, enqueueing, sending at a pace.

Until 3.4 this was a set of nested functions inside `create()`. Pulled out because it has no request
dependency, because the batch mode (goal 2) attaches exactly here, and because no mail may go out
before the tokens are durable (B7) -- see notes/plan.md §11.

*(This said "because SMTP must not run inside the request transaction". There never was a request
transaction: Django did not read the module-wide `ATOMIC_REQUESTS`, B16. The finding stands, only
the reasoning was wrong -- `create()` used to send the mails **inside the save loop**, while the
tokens were still being created.)*

**Since the paced sender (plan §11.7) there are two separate halves here**, and the split is
deliberate -- it is the shape Django's future `django.tasks` has as well (§11.7, 6a):

* **Enqueueing** (`enqueue`) happens in the request, in the same transaction as the tokens.
* **Sending** (`send_pending`) happens in another process, invoked by the management command
  `send_pending_mails`. `deliver()` -- which sent everything immediately -- is gone; it was the
  place that plan §11.1 said a batch sender would replace.

The texts live in `vote/templates/vote/mail/` and reproduce the former `VOTE_*_MAIL_TEXT` settings
**word for word**; `vote/tests/test_mail_service.py` nails that down. Autoescaping is off in those
templates: these are plain text mails, and an `&` in a poll title must not arrive as `&amp;`.
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

#: How often a message may be rejected before it is given up on. **Only** rejections by the server
#: for this very message count -- an unreachable server costs no attempt, otherwise an hour-long
#: outage would throw the invitations away one by one. At a one-minute pace, ten rejections of the
#: same message span ten minutes; whoever rejects that one address for that long is rejecting it,
#: not throttling.
MAX_ATTEMPTS = 10


def _absolute(path):
    """Turns a Django path into an address that belongs in a mail."""
    return settings.VOTE_BASE_URL + path


def _render(name, context):
    """Subject and body from two templates. The subject must not contain a line break."""
    subject = render_to_string(f"vote/mail/{name}_subject.txt", context).strip()
    body = render_to_string(f"vote/mail/{name}_body.txt", context)
    return subject, body


def creator_message(poll, creator_mail, creator_token):
    """The mail to the creator, with the management link and the management token."""
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
    """The invitation to one voter, with the voting link and the token in it."""
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
    """What became of one attempt to send. What happens to the row follows from this."""

    SENT = "sent"
    #: The server rejected *this* message permanently (5xx), or it cannot be encoded.
    PERMANENT = "permanent"
    #: The server rejected *this* message for now (4xx) -- the `450` of throttling.
    TRANSIENT = "transient"
    #: The server was unreachable or went away. No verdict about the message.
    UNREACHABLE = "unreachable"


def _smtp_code(error):
    """The response code from an smtplib exception, or `None` when there is none.

    Two forms occur: `SMTPResponseException` carries `smtp_code` directly, `SMTPRecipientsRefused`
    carries a `(code, text)` pair per recipient. There is exactly one recipient per message here, so
    it is exactly one code.
    """
    code = getattr(error, "smtp_code", None)
    if code is not None:
        return code
    refused = getattr(error, "recipients", None) or {}
    codes = [value[0] for value in refused.values() if value]
    return min(codes) if codes else None


def _send_one(connection, row):
    """Sends one row and says what became of it. Does not raise."""
    try:
        # `fail_silently=False` stays: the exception *is* the information. It takes effect because
        # `send_mail` with a `connection` handed to it uses that connection's `fail_silently` -- and
        # `get_connection()` leaves it False.
        send_mail(
            row.subject,
            row.body,
            settings.VOTE_MAIL_FROM,
            [row.recipient],
            fail_silently=False,
            connection=connection,
        )
    except (UnicodeEncodeError, BadHeaderError):
        # R5-1: a row that **cannot** be turned into a message at all is a case of its own -- no
        # retry makes it better. `BadHeaderError` inherits from `ValueError`, not from
        # `SMTPException`, and therefore flew all the way into the command; because the row stays at
        # the front of the queue, sending was then stopped for *every* poll.
        logger.exception("Umfrage-Mail lässt sich nicht als Nachricht aufbauen und wird verworfen")
        return _Outcome.PERMANENT
    except (SMTPResponseException, SMTPRecipientsRefused) as error:
        code = _smtp_code(error)
        if code is not None and 400 <= code < 500:
            return _Outcome.TRANSIENT
        # R6-1: the code belongs in the log, and here, where it is known. The message used to sit in
        # the caller without it, and from "a mail was rejected" there was no way to tell whether an
        # address was wrong or the server was being difficult. A code is a number, not an address
        # (F8).
        logger.warning("Eine Umfrage-Mail wurde mit SMTP-Code %s dauerhaft abgelehnt", code)
        return _Outcome.PERMANENT
    except (SMTPException, OSError):
        # Connection gone, DNS broken, timeout. **No verdict about the message** -- which is why
        # `attempts` is not incremented here, see MAX_ATTEMPTS.
        logger.exception("Mailserver nicht erreichbar, Versand abgebrochen")
        return _Outcome.UNREACHABLE
    return _Outcome.SENT


def enqueue(messages):
    """Puts rendered messages into the queue.

    **Belongs in the same transaction as the tokens** and is therefore deliberately *not* an
    `on_commit` callback: if it ran afterwards, a crash in between could leave tokens without an
    invitation -- voters who never learn their token, and a poll only the creator can still close.
    The promise from B7 ("no mail before the tokens are durable") holds anyway, and structurally:
    sending happens in another process, and that one only sees committed rows.
    """
    return OutgoingMail.objects.bulk_create(
        [
            OutgoingMail(subject=subject, body=body, recipient=recipient)
            for subject, body, recipient in messages
        ]
    )


def send_pending(*, batch_size=None, pause=None, sleep=time.sleep):
    """Sends the queue at a pace: `batch_size` messages, then `pause` seconds.

    Invoked by the management command `send_pending_mails`, never from a request -- a run takes
    minutes. Returns a summary as a dict (`sent`, `given_up`, `batches`, `remaining`); the command
    writes it to stdout. *(This listed `deferred` -- that key existed in the first draft, it went
    away with the accounting mistake `_finish()` describes, and stayed in the docstring. Review
    R14-2.)*

    **The one rule everything depends on: no `sleep` inside a transaction.** Measured (notes/plan.md
    §11.7, 4a): a short transaction per mail with `sleep` outside costs a concurrent vote 7--9 ms,
    **regardless of how long the run takes**. A transaction spanning the pause makes votes wait
    seconds first and then get lost, as soon as the run takes longer than the `timeout` of 20 s --
    measured, 8 out of 200. That is why there is no `atomic()` around the loop anywhere here, and
    `save()`/`delete()` per row are each their own short transaction.

    **Send, then delete** -- not the other way around. If the process dies in between, the mail goes
    out twice; it carries the same single-use token, so a duplicate invitation is harmless. The
    reverse mistake *loses* an invitation, and then a token is missing forever: the poll no longer
    closes by itself.

    **On the first transient failure the run stops**, instead of driving the remaining 29 into the
    same wall. A `450` means "you are over the limit"; the next timer invocation meets a window that
    has been reset. A *permanent* failure (5xx) concerns only that one address, and there the batch
    carries on.

    A **separate connection per batch**: the pause should not be spent inside an open connection,
    and the batch boundary is the natural place for that. Within a batch it stays one connection for
    30 messages instead of 30 connections.
    """
    batch_size = settings.VOTE_MAIL_BATCH_SIZE if batch_size is None else batch_size
    pause = settings.VOTE_MAIL_BATCH_PAUSE if pause is None else pause
    summary = {"sent": 0, "given_up": 0, "batches": 0}

    previous_head = None
    while True:
        rows = list(OutgoingMail.objects.order_by("pk")[:batch_size])
        if not rows:
            return _finish(summary)
        if rows[0].pk == previous_head:
            # A watchdog (R5-2). Otherwise the loop ends solely because every exit either deletes
            # the row or breaks off -- a fifth case that does neither spins forever and holds the
            # `flock` while doing so, which means no mail goes out at all any more. The same front
            # row twice means: this pass moved nothing.
            logger.error(
                "Versand kommt nicht voran, Lauf abgebrochen -- %s Zeilen liegen noch",
                OutgoingMail.objects.count(),
            )
            return _finish(summary)
        previous_head = rows[0].pk
        if summary["batches"]:
            # The pause lies **between** the batches: not before the first (otherwise every run
            # waits for nothing) and not after the last (otherwise the command holds the lock longer
            # than it works).
            sleep(pause)
        summary["batches"] += 1
        if _send_batch(rows, summary):
            return _finish(summary)


def _finish(summary):
    """What is still queued is *counted* at the end rather than tracked per row.

    The first attempt tracked it per row and compared cumulative sums against the size of one batch
    -- which produced wrong numbers as soon as there was more than one batch.
    """
    summary["remaining"] = OutgoingMail.objects.count()
    return summary


def _send_batch(rows, summary):
    """Sends one batch. Returns True when the whole run should stop."""
    if not settings.VOTE_SEND_MAILS:
        # As `deliver()` did before: with sending switched off, just print, so that what would have
        # gone out is visible locally. The rows disappear anyway, otherwise the run would go over
        # the same queue forever.
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
                # `_send_one()` has already logged it, that is where the reason is known (R6-1) --
                # **without** the address and without a poll identifier (F8). The text of an
                # exception may contain the address; where `logger.exception` stands, that has been
                # weighed under F8 and accepted.
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
                # Unreachable: the row stays as it is, **without** an attempt. An hour-long outage
                # must not throw the invitations away one by one.
                return True
    finally:
        try:
            connection.close()
        except (SMTPException, OSError):
            # `close()` can raise on QUIT. That must not end the run -- the mails of this batch are
            # out and their rows deleted.
            logger.exception("SMTP-Verbindung ließ sich nicht ordentlich schließen")
    return False


def poll_created_messages(poll, creator_mail, voter_mails, tokens):
    """Every mail of a newly created poll, in sending order: creator, then voters.

    Renders everything up front: sending runs later in another process and then only reads the
    queue, without needing the poll or the tokens (plan §11.7).

    **The pairing is shuffled** (review R1-2). `bulk_create` creates the tokens in the order of the
    addresses entered, so the `id`s ran parallel to the recipient list -- and the list does not
    survive the run, the `id`s do. Whoever knew the list and could read the database could see from
    the remaining `id`s *who* had not voted yet. Shuffled, the order says nothing any more. The vote
    itself was never affected by this, it carries no identifier.
    """
    tokens = list(tokens)
    random.SystemRandom().shuffle(tokens)
    messages = [creator_message(poll, creator_mail, poll.creator_token)]
    for voter_mail, token in zip(voter_mails, tokens, strict=True):
        messages.append(voter_message(poll, voter_mail, token.token_string))
    return messages
