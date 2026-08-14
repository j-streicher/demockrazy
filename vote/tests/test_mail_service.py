"""Tests for vote/services/mail.py -- above all: the wording of the mails.

Until 3.4 the texts sat in `demockrazy/settings.py` as `%`-formatted strings and are Django
templates now. That must have changed **nothing** about the wording (plan rule 3/6: no silent
changes to mail texts). The expected values below are the settings strings from before the rebuild,
deliberately written out as literals here: that way the test depends neither on the settings nor on
the templates, and it fires when either side moves.
"""

from smtplib import SMTPException, SMTPRecipientsRefused, SMTPServerDisconnected
from typing import ClassVar

import pytest
from django.core.mail.backends.base import BaseEmailBackend

from vote.models import OutgoingMail, Poll, Token
from vote.services import mail
from vote.tests.mailtrap import MailTrap

# The wording before 3.4, from settings.VOTE_ADMIN_MAIL_SUBJECT / VOTE_ADMIN_MAIL_TEXT.
CREATOR_SUBJECT = "[democrazy] Poll 'Testabstimmung' created"
CREATOR_BODY = """
Hi, you just created a new poll with title 'Testabstimmung' that is manageable at http://testserver/vote/IDENT/manage
Your admin token is: CREATORTOKEN

Thank you for traveling with Deutsche Bahn"

"""

# The wording before 3.4, from settings.VOTE_MAIL_SUBJECT / VOTE_MAIL_TEXT.
VOTER_SUBJECT = "[demockrazy] Deine Stimme für 'Testabstimmung'"
VOTER_BODY = """
Hallo,

Jemand hat eine Abstimmung mit dem Titel 'Testabstimmung' auf http://testserver erstellt.
Du wurdest eingeladen an dieser Abstimmung teilzunehmen.

Dies ist dir über folgenden Link möglich:
http://testserver/vote/IDENT/?token=TOK

Nach Abgabe deiner Stimme wird der Token aus der Datenbank gelöscht.
Dadurch gibt es keine Korrelation zwischen Token (Teilnehmer) und abgegebener Stimme.

Die Umfrage wird automatisch beendet, sobald alle Tokens verbraucht wurden. Nach Beendigung sind die Umfrageergebnisse sichtbar.
Der Ersteller der Umfrage hat die möglichkeit diese vorzeitig zu beenden.

XoXoXo
Die Wahlleitung

"""


@pytest.fixture
def poll(db):
    return Poll.objects.create(
        title="Testabstimmung", question_text="?", identifier="IDENT", num_tokens=1
    )


class TestWording:
    def test_creator_mail_is_unchanged(self, poll):
        subject, body, recipient = mail.creator_message(poll, "admin@example.org", "CREATORTOKEN")
        assert subject == CREATOR_SUBJECT
        assert body == CREATOR_BODY
        assert recipient == "admin@example.org"

    def test_voter_mail_is_unchanged(self, poll):
        subject, body, recipient = mail.voter_message(poll, "a@example.org", "TOK")
        assert subject == VOTER_SUBJECT
        assert body == VOTER_BODY
        assert recipient == "a@example.org"


class TestRendering:
    def test_no_html_escaping_in_the_body(self, poll):
        """A plain text mail: an `&` in the title must not arrive as `&amp;`."""
        poll.title = "Bier & Brezn <heute>"
        _, body, _ = mail.voter_message(poll, "a@example.org", "TOK")
        assert "Bier & Brezn <heute>" in body
        assert "&amp;" not in body
        assert "&lt;" not in body

    def test_no_html_escaping_in_the_subject(self, poll):
        poll.title = "Bier & Brezn"
        subject, _, _ = mail.voter_message(poll, "a@example.org", "TOK")
        assert subject == "[demockrazy] Deine Stimme für 'Bier & Brezn'"

    def test_apostrophe_in_the_title_survives(self, poll):
        """The title appears in single quotes in both texts."""
        poll.title = "Gehen wir's an"
        _, body, _ = mail.creator_message(poll, "admin@example.org", "T")
        assert "'Gehen wir's an'" in body
        assert "&#x27;" not in body

    def test_subject_has_no_newline(self, poll):
        """send_mail() wirft bei einem Zeilenumbruch im Betreff (Header-Injection)."""
        for subject, _, _ in [
            mail.creator_message(poll, "admin@example.org", "T"),
            mail.voter_message(poll, "a@example.org", "TOK"),
        ]:
            assert "\n" not in subject
            assert subject == subject.strip()


class TestPollCreatedMessages:
    def test_creator_first_then_voters(self, poll):
        tokens = [Token.objects.create(poll=poll, token_string=f"t{i}") for i in range(2)]
        messages = mail.poll_created_messages(
            poll, "admin@example.org", ["a@example.org", "b@example.org"], tokens
        )
        assert [recipient for _, _, recipient in messages] == [
            "admin@example.org",
            "a@example.org",
            "b@example.org",
        ]

    def test_each_voter_gets_exactly_one_of_the_tokens(self, poll):
        """One each, none twice, none left over -- but **not** in a fixed order.

        This used to read `"?token=t0" in links[0]`, which is exactly the pairing R1-2 undid. What
        is checked now is the property that matters: a bijection.
        """
        tokens = [Token.objects.create(poll=poll, token_string=f"t{i}") for i in range(5)]
        voters = [f"w{i}@example.org" for i in range(5)]
        messages = mail.poll_created_messages(poll, "admin@example.org", voters, tokens)

        handed_out = []
        for _, body, recipient in messages[1:]:
            found = [
                token.token_string for token in tokens if f"?token={token.token_string}" in body
            ]
            assert len(found) == 1, (recipient, found)
            handed_out.append(found[0])
        assert sorted(handed_out) == sorted(token.token_string for token in tokens)

    def test_the_pairing_does_not_follow_the_recipient_order(self, poll):
        """R1-2: the token `id`s ran parallel to the recipient list, and the `id`s remain.

        Measured, it went like this: address 1 got token 1 ... address 5 got token 5. After the run
        no address is in the database any more, but the `id` order is -- whoever knew the list and
        could read the database could tell from the remaining `id`s *who* had already voted. The
        vote itself was never affected.

        Ten polls with six recipients each: **all** ten hitting the identity by chance has
        probability (1/720)^10.
        """
        voters = [f"w{i}@example.org" for i in range(6)]
        unchanged = 0
        for round_number in range(10):
            tokens = [
                Token.objects.create(poll=poll, token_string=f"r{round_number}t{i}")
                for i in range(6)
            ]
            messages = mail.poll_created_messages(poll, "admin@example.org", voters, tokens)
            order = [
                next(token.pk for token in tokens if f"?token={token.token_string}" in body)
                for _, body, _ in messages[1:]
            ]
            if order == sorted(order):
                unchanged += 1
        assert unchanged < 10, "the pairing still follows the input order"

    def test_mismatched_token_count_is_an_error(self, poll):
        """A voter without a token (or the reverse) is a programming error, not a silent edge case."""
        tokens = [Token.objects.create(poll=poll, token_string="t0")]
        with pytest.raises(ValueError):
            mail.poll_created_messages(poll, "admin@example.org", ["a@x.org", "b@x.org"], tokens)


class CountingBackend(BaseEmailBackend):
    """A mail backend that records *when* a connection is opened, and stages failures.

    No Django backend shows that: `locmem` skips connections entirely, `smtp` would need a server.
    The semantics of `open()`/`close()` are therefore modelled on the SMTP backend -- open stays
    open, a second `open()` is a no-op.

    Driven through class attributes, because Django instantiates the backend itself and it cannot be
    handed any arguments.
    """

    #: The log in order: "open", "close" and the recipient addresses.
    log: ClassVar[list] = []
    #: Recipients the server rejects for now with a 450 -- the shape of throttling.
    refuse_temporarily: ClassVar[tuple] = ()
    #: Recipients the server rejects permanently with a 550.
    refuse_permanently: ClassVar[tuple] = ()
    #: Server not reachable at all: `open()` breaks off.
    unreachable: ClassVar[bool] = False
    #: Whether `close()` raises while cleaning up -- which the real SMTP backend can do on QUIT.
    fail_on_close: ClassVar[bool] = False

    @classmethod
    def reset(cls):
        cls.log = []
        cls.refuse_temporarily = ()
        cls.refuse_permanently = ()
        cls.unreachable = False
        cls.fail_on_close = False

    @classmethod
    def recipients(cls):
        return [entry for entry in cls.log if "@" in entry]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = None

    def open(self):
        if self.connection is not None:
            return False
        if CountingBackend.unreachable:
            raise SMTPServerDisconnected("connection gone")
        self.connection = object()
        CountingBackend.log.append("open")
        return True

    def close(self):
        if self.connection is None:
            return
        self.connection = None
        CountingBackend.log.append("close")
        if CountingBackend.fail_on_close:
            raise SMTPException("QUIT failed")

    def send_messages(self, email_messages):
        self.open()
        for message in email_messages:
            # `message()` really builds the message -- so this double checks the same headers a real
            # backend does (Django's locmem backend does it for the same reason). Without the call
            # it accepted messages no mail server would ever have seen: the `BadHeaderError` from
            # R5-1 arises exactly here.
            message.message()
            recipient = message.to[0]
            if recipient in CountingBackend.refuse_temporarily:
                raise SMTPRecipientsRefused(
                    {recipient: (450, b"4.7.1 Error: too much mail from <sender>")}
                )
            if recipient in CountingBackend.refuse_permanently:
                raise SMTPRecipientsRefused({recipient: (550, b"5.1.1 User unknown")})
            CountingBackend.log.append(recipient)
        return len(email_messages)


@pytest.fixture
def counting_backend(settings):
    settings.EMAIL_BACKEND = f"{__name__}.CountingBackend"
    settings.VOTE_SEND_MAILS = True
    CountingBackend.reset()
    yield CountingBackend
    CountingBackend.reset()


@pytest.fixture
def recorded_sleep():
    """Records the pauses instead of waiting them out. Without it the suite took minutes."""
    calls = []
    return calls.append, calls


def enqueue(count, first="a"):
    mail.enqueue([(f"Betreff {i}", f"Text {i}", f"{first}{i}@example.org") for i in range(count)])
    return list(OutgoingMail.objects.order_by("pk"))


@pytest.mark.django_db
class TestEnqueue:
    def test_one_row_per_message_in_order(self):
        rows = enqueue(3)
        assert [row.recipient for row in rows] == [
            "a0@example.org",
            "a1@example.org",
            "a2@example.org",
        ]
        assert [row.subject for row in rows] == ["Betreff 0", "Betreff 1", "Betreff 2"]
        assert {row.attempts for row in rows} == {0}

    def test_nothing_is_sent_by_enqueueing(self, counting_backend):
        enqueue(3)
        assert counting_backend.log == []


@pytest.mark.django_db
class TestSendPending:
    """The paced sender (plan §11.7). This used to be `deliver()` and sent immediately."""

    def test_the_queue_is_emptied_and_the_mails_go_out(self, counting_backend):
        enqueue(3)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == [
            "a0@example.org",
            "a1@example.org",
            "a2@example.org",
        ]
        assert OutgoingMail.objects.count() == 0
        assert summary == {"sent": 3, "given_up": 0, "batches": 1, "remaining": 0}

    def test_one_connection_per_batch(self, counting_backend):
        """Every send_mail() call used to build its own: 101 mails = 101 connections.

        The connection ends at the batch boundary, so the pause is not spent inside an open connection
        -- within a batch it stays one for all the messages.
        """
        enqueue(20)
        mail.send_pending(batch_size=5, pause=0)
        assert counting_backend.log.count("open") == 4
        assert counting_backend.log.count("close") == 4
        assert len(counting_backend.recipients()) == 20

    def test_the_pause_lies_between_the_batches(self, counting_backend, recorded_sleep):
        """
        Not before the first batch (or every run waits for nothing) and not after the last one (or
        the command holds its lock longer than it works)."""
        sleep, calls = recorded_sleep
        enqueue(9)
        summary = mail.send_pending(batch_size=3, pause=2, sleep=sleep)
        assert summary["batches"] == 3
        assert calls == [2, 2], "zwei Pausen bei drei Batches"

    def test_a_single_batch_never_pauses(self, counting_backend, recorded_sleep):
        sleep, calls = recorded_sleep
        enqueue(2)
        mail.send_pending(batch_size=30, pause=2, sleep=sleep)
        assert calls == []

    def test_an_empty_queue_opens_nothing(self, counting_backend, recorded_sleep):
        sleep, calls = recorded_sleep
        summary = mail.send_pending(pause=2, sleep=sleep)
        assert counting_backend.log == []
        assert calls == []
        assert summary == {"sent": 0, "given_up": 0, "batches": 0, "remaining": 0}

    def test_a_permanent_rejection_drops_the_row_and_the_batch_continues(self, counting_backend):
        """A 5xx concerns that one address -- the rest of the batch goes out."""
        counting_backend.refuse_permanently = ("a1@example.org",)
        enqueue(3)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == ["a0@example.org", "a2@example.org"]
        assert OutgoingMail.objects.count() == 0, "auch die abgelehnte Zeile ist weg"
        assert summary["sent"] == 2
        assert summary["given_up"] == 1

    def test_the_log_names_the_smtp_code_but_no_address(self, counting_backend, caplog):
        """R6-1: the log line named no reason -- and the comment beside it claimed the opposite.

        Measured, it was exactly one line: "Eine Umfrage-Mail wurde dauerhaft abgelehnt und
        verworfen", without `exc_info`, without a code. So from the journal there was no way to
        decide whether an address was wrong or the server was being difficult. The address still
        does **not** belong in there (F8); an SMTP code is a number.
        """
        counting_backend.refuse_permanently = ("a1@example.org",)
        enqueue(3)
        with caplog.at_level("WARNING"):
            mail.send_pending(pause=0)

        assert "550" in caplog.text
        assert "a1@example.org" not in caplog.text

    def test_a_transient_rejection_stops_the_run(self, counting_backend):
        """
        The `450` of throttling. Carrying on would mean driving the remaining 29 into the same wall
        -- the next timer invocation meets a window that has been reset."""
        counting_backend.refuse_temporarily = ("a1@example.org",)
        enqueue(4)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == ["a0@example.org"]
        assert summary["sent"] == 1
        assert summary["remaining"] == 3, "the rejected row and the two behind it are still queued"
        assert OutgoingMail.objects.get(recipient="a1@example.org").attempts == 1

    def test_a_transient_rejection_is_given_up_eventually(self, counting_backend):
        counting_backend.refuse_temporarily = ("a0@example.org",)
        enqueue(1)
        for _ in range(mail.MAX_ATTEMPTS):
            mail.send_pending(pause=0)
        assert OutgoingMail.objects.count() == 0, "at some point it is given up on"

    def test_an_unreachable_server_costs_no_attempt(self, counting_backend):
        """Otherwise an hour-long outage would throw the invitations away one by one.

        The server said nothing about *this* message -- so there is no verdict about it.
        """
        counting_backend.unreachable = True
        enqueue(3)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == []
        assert summary == {"sent": 0, "given_up": 0, "batches": 1, "remaining": 3}
        assert {row.attempts for row in OutgoingMail.objects.all()} == {0}

    def test_a_failure_while_closing_does_not_escape(self, counting_backend):
        """The mails of this batch are out and their rows deleted -- a QUIT that goes wrong must not
        turn that into an abort."""
        counting_backend.fail_on_close = True
        enqueue(2)
        summary = mail.send_pending(pause=0)
        assert summary["sent"] == 2
        assert OutgoingMail.objects.count() == 0

    def test_nothing_is_sent_when_sending_is_disabled(self, counting_backend, settings, capsys):
        """With sending off, no connection appears. The rows disappear anyway -- otherwise the run
        would go over the same queue forever."""
        settings.VOTE_SEND_MAILS = False
        enqueue(2)
        mail.send_pending(pause=0)
        assert counting_backend.log == []
        assert OutgoingMail.objects.count() == 0
        assert "Betreff 0" in capsys.readouterr().out

    def test_the_defaults_come_from_the_settings(self, counting_backend, recorded_sleep, settings):
        """The two numbers were given by the user and have to stay configurable."""
        sleep, calls = recorded_sleep
        settings.VOTE_MAIL_BATCH_SIZE = 2
        settings.VOTE_MAIL_BATCH_PAUSE = 7
        enqueue(4)
        assert mail.send_pending(sleep=sleep)["batches"] == 2
        assert calls == [7]

    def test_the_pacing_values_are_the_ones_the_user_asked_for(self):
        """R10-3: the pacing was configurable, but nothing nailed down its *values*.

        Batches of 30 with a 2 s pause were given by the user, and production uses exactly these
        defaults -- but the tests above always pass `batch_size`/`pause` explicitly, so a change to
        the defaults went unnoticed (measured by mutation: 30 -> 1000 escaped the whole suite).
        """
        from django.conf import settings as django_settings

        assert (django_settings.VOTE_MAIL_BATCH_SIZE, django_settings.VOTE_MAIL_BATCH_PAUSE) == (
            30,
            2,
        ), (
            "Given by the user (plan §11.7). If this is meant to be different on purpose, the reason "
            "belongs in the notes -- and if this test fails locally, DEMOCKRAZY_MAIL_BATCH_SIZE/_PAUSE "
            "is probably set in the environment."
        )

    def test_a_silent_mail_server_cannot_block_forever(self):
        """`EMAIL_TIMEOUT` has to be finite. Django's default is `None`, so unlimited.

        Looked up rather than assumed: with `None` the SMTP backend does not pass `timeout` on to
        `smtplib`, which takes the socket default, and that is `None` as well. A server that accepts
        the connection and then goes quiet therefore holds a uwsgi process -- and there are four.
        For the paced sender it is worse: it locks itself out, a run without end holds the lock, and
        then no mail goes out at all.
        """
        from django.conf import settings as django_settings

        assert django_settings.EMAIL_TIMEOUT is not None
        assert 0 < django_settings.EMAIL_TIMEOUT <= 60


@pytest.mark.django_db
class TestUnsendableRowDoesNotStopTheRun:
    """R5-1: a row that cannot be built into a message costs only itself.

    The finding: a line break in the poll title ended up in the subject, Django's
    `forbid_multi_line_headers` raised a `BadHeaderError` -- a `ValueError` subclass covered neither
    by `SMTPException` nor by `OSError`. It flew all the way into the management command, and
    because the row stayed at the front of the queue, every further timer invocation died in the
    same place: no sending any more, for any poll.
    """

    def test_the_run_survives_it_and_the_others_go_out(self, counting_backend):
        OutgoingMail.objects.create(
            recipient="erste@example.org", subject="Poll 'a\nBcc: x@y.z' created", body="hi"
        )
        OutgoingMail.objects.create(recipient="zweite@example.org", subject="harmlos", body="hi")

        summary = mail.send_pending(pause=0)

        assert counting_backend.recipients() == ["zweite@example.org"]
        assert summary == {"sent": 1, "given_up": 1, "batches": 1, "remaining": 0}
        assert OutgoingMail.objects.count() == 0, "the broken row has to disappear"

    def test_a_poll_created_through_the_form_cannot_produce_such_a_row(self, client):
        """The other half of the fix: the form no longer lets the line break through."""
        response = client.post(
            "/vote/create",
            {
                "title": "Kaffee\nBcc: leak@example.org",
                "type": "simple_choice",
                "description": "d",
                "choices": "ja\nnein",
                "creator_mail": "chef@example.org",
                "voter_mails": "v@example.org",
            },
        )
        assert response.status_code == 200
        assert response.context["form"].errors["title"]
        assert OutgoingMail.objects.count() == 0


@pytest.mark.django_db
class TestTheRunCannotSpin:
    """R5-2: the loop ends even when a pass moves nothing.

    This came up by accident: a mutation that removed the branch for "server unreachable" -- so a
    line that neither deletes nor breaks off -- sent the test suite into an endless loop that was
    still running after nine minutes, **without** a failing test. In production that would be worse
    than a crash: the run holds the `flock`, so afterwards no mail goes out at all, and from the
    outside "hanging" looks like "still working".
    """

    def test_a_batch_that_changes_nothing_ends_the_run(self, monkeypatch, caplog):
        enqueue(3)
        monkeypatch.setattr(mail, "_send_batch", lambda rows, summary: False)

        summary = mail.send_pending(pause=0)

        assert summary == {"sent": 0, "given_up": 0, "batches": 1, "remaining": 3}
        assert "kommt nicht voran" in caplog.text

    def test_the_guard_does_not_trip_on_a_normal_multi_batch_run(self, counting_backend):
        """The counter-check: as long as something disappears, the queue drains normally."""
        enqueue(7)
        summary = mail.send_pending(batch_size=2, pause=0)
        assert summary == {"sent": 7, "given_up": 0, "batches": 4, "remaining": 0}


@pytest.mark.django_db
class TestARealServerThatThrottles:
    """R10-4: the one test here that speaks SMTP over a socket, against `mailtrap.MailTrap`.

    Every other test on this page raises the rejection by hand through `CountingBackend` -- and it
    raised the wrong exception. Measured through Django's own SMTP backend, a server that throttles
    answers `450` to DATA, and smtplib turns that into `SMTPDataError`: `smtp_code` is set and there
    is no `recipients`. `CountingBackend` only ever produced the `SMTPRecipientsRefused` form, so
    the branch of `mail._smtp_code` that production actually takes was covered by nothing -- setting
    it to `None` left all 261 tests green. The cost of that branch failing is not cosmetic: without
    a code the `450` counts as permanent and the throttled invitation is dropped instead of retried.
    """

    def test_a_real_450_leaves_the_row_for_the_next_run(self, settings):
        with MailTrap(limit=1) as trap:
            settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
            settings.EMAIL_HOST = "127.0.0.1"
            settings.EMAIL_PORT = trap.port
            settings.EMAIL_USE_TLS = False
            settings.VOTE_SEND_MAILS = True
            enqueue(3)

            summary = mail.send_pending(pause=0)

        assert trap.accepted == ["a0@example.org"], "the first one got through"
        assert trap.throttled == ["a1@example.org"], "and the run stopped at the second"
        assert summary == {"sent": 1, "given_up": 0, "batches": 1, "remaining": 2}
        assert OutgoingMail.objects.get(recipient="a1@example.org").attempts == 1
