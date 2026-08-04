"""Tests für vote/services/mail.py -- vor allem: der Wortlaut der Mails.

Die Texte lagen bis 3.4 als `%`-formatierte Strings in `demockrazy/settings.py` und sind jetzt
Django-Templates. Das darf am Wortlaut **nichts** geändert haben (Plan-Regel 3/6: keine stillen
Änderungen an Mail-Texten). Die Erwartungswerte unten sind die Settings-Strings von vor dem Umbau,
hier absichtlich als Literale ausgeschrieben: damit hängt der Test weder an den Settings noch an
den Templates und schlägt an, wenn sich eine der beiden Seiten bewegt.
"""

from smtplib import SMTPException
from typing import ClassVar

import pytest
from django.core.mail.backends.base import BaseEmailBackend

from vote.models import Poll, Token
from vote.services import mail

# Wortlaut vor 3.4, aus settings.VOTE_ADMIN_MAIL_SUBJECT / VOTE_ADMIN_MAIL_TEXT.
CREATOR_SUBJECT = "[democrazy] Poll 'Testabstimmung' created"
CREATOR_BODY = """
Hi, you just created a new poll with title 'Testabstimmung' that is manageable at http://testserver/vote/IDENT/manage
Your admin token is: CREATORTOKEN

Thank you for traveling with Deutsche Bahn"

"""

# Wortlaut vor 3.4, aus settings.VOTE_MAIL_SUBJECT / VOTE_MAIL_TEXT.
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
        """Plain-Text-Mail: ein `&` im Titel darf nicht als `&amp;` beim Empfänger landen."""
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
        """Der Titel steht in den Texten in einfachen Anführungszeichen."""
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

    def test_each_voter_gets_their_own_token_link(self, poll):
        tokens = [Token.objects.create(poll=poll, token_string=f"t{i}") for i in range(2)]
        messages = mail.poll_created_messages(
            poll, "admin@example.org", ["a@example.org", "b@example.org"], tokens
        )
        links = [body for _, body, _ in messages[1:]]
        assert "?token=t0" in links[0]
        assert "?token=t1" in links[1]

    def test_mismatched_token_count_is_an_error(self, poll):
        """Ein Wähler ohne Token (oder umgekehrt) ist ein Programmierfehler, kein stiller Sonderfall."""
        tokens = [Token.objects.create(poll=poll, token_string="t0")]
        with pytest.raises(ValueError):
            mail.poll_created_messages(poll, "admin@example.org", ["a@x.org", "b@x.org"], tokens)


class CountingBackend(BaseEmailBackend):
    """Ein Mail-Backend, das protokolliert, *wann* eine Verbindung entsteht.

    Es gibt kein Django-Backend, das das zeigt: `locmem` überspringt Verbindungen ganz, `smtp`
    bräuchte einen Server. Die Semantik von `open()`/`close()` ist deshalb der des
    SMTP-Backends nachgebildet -- offen bleibt offen, ein zweites `open()` ist ein No-op.

    Gesteuert über Klassenattribute, weil Django das Backend selbst instanziiert und man ihm
    keine Argumente mitgeben kann.
    """

    #: Protokoll in Reihenfolge: "open", "close" und die Empfängeradressen.
    log: ClassVar[list] = []
    #: Empfänger, bei denen der Versand mit einer SMTPException scheitert.
    fail_for: ClassVar[tuple] = ()
    #: Ob `close()` beim Aufräumen wirft -- was das echte SMTP-Backend beim QUIT kann.
    fail_on_close = False

    @classmethod
    def reset(cls):
        cls.log = []
        cls.fail_for = ()
        cls.fail_on_close = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = None

    def open(self):
        if self.connection is not None:
            return False
        self.connection = object()
        CountingBackend.log.append("open")
        return True

    def close(self):
        if self.connection is None:
            return
        self.connection = None
        CountingBackend.log.append("close")
        if CountingBackend.fail_on_close:
            raise SMTPException("QUIT fehlgeschlagen")

    def send_messages(self, email_messages):
        self.open()
        for message in email_messages:
            recipient = message.to[0]
            if recipient in CountingBackend.fail_for:
                raise SMTPException(f"450 4.7.1 Error: too much mail from <{recipient}>")
            CountingBackend.log.append(recipient)
        return len(email_messages)


@pytest.fixture
def counting_backend(settings):
    settings.EMAIL_BACKEND = f"{__name__}.CountingBackend"
    settings.VOTE_SEND_MAILS = True
    CountingBackend.reset()
    yield CountingBackend
    CountingBackend.reset()


def _messages(count, first="a"):
    return [(f"Betreff {i}", f"Text {i}", f"{first}{i}@example.org") for i in range(count)]


class TestDeliver:
    """Was `deliver()` zusagt: eine Verbindung, und ein Fehler hält die übrigen nicht auf."""

    def test_one_connection_for_many_messages(self, counting_backend):
        """Vorher baute jeder send_mail()-Aufruf seine eigene: 101 Mails = 101 Verbindungen."""
        mail.deliver(_messages(20))
        assert counting_backend.log.count("open") == 1
        assert counting_backend.log.count("close") == 1
        assert len([entry for entry in counting_backend.log if "@" in entry]) == 20

    def test_the_connection_is_closed_even_when_everything_fails(self, counting_backend):
        counting_backend.fail_for = tuple(recipient for _, _, recipient in _messages(3))
        mail.deliver(_messages(3))
        assert counting_backend.log.count("close") == 1

    def test_one_unreachable_recipient_does_not_stop_the_others(self, counting_backend):
        """Die Zusage aus 3.4, jetzt direkt geprüft statt nur über die View."""
        counting_backend.fail_for = ("a1@example.org",)
        mail.deliver(_messages(3))
        assert [entry for entry in counting_backend.log if "@" in entry] == [
            "a0@example.org",
            "a2@example.org",
        ]

    def test_a_failure_while_closing_does_not_escape(self, counting_backend):
        """`deliver()` läuft als on_commit-Callback im Request -- ein Fehler daraus wäre ein 500.

        Die Umfrage ist zu diesem Zeitpunkt schon angelegt und die Mails sind raus; ein QUIT, das
        schiefgeht, darf daraus keine Fehlerseite machen.
        """
        counting_backend.fail_on_close = True
        mail.deliver(_messages(2))
        assert [entry for entry in counting_backend.log if "@" in entry] == [
            "a0@example.org",
            "a1@example.org",
        ]

    def test_nothing_is_sent_when_sending_is_disabled(self, counting_backend, settings, capsys):
        """Ohne Versand entsteht auch keine Verbindung -- es gibt nichts zu verbinden."""
        settings.VOTE_SEND_MAILS = False
        mail.deliver(_messages(2))
        assert counting_backend.log == []
        assert "Betreff 0" in capsys.readouterr().out

    def test_an_empty_list_opens_nothing(self, counting_backend):
        mail.deliver([])
        assert counting_backend.log == []

    def test_a_silent_mail_server_cannot_block_forever(self):
        """`EMAIL_TIMEOUT` muss endlich sein. Djangos Default ist `None`, also unbegrenzt.

        Nachgesehen statt vermutet: bei `None` gibt das SMTP-Backend `timeout` nicht an `smtplib`
        weiter, das nimmt den Socket-Default, und der ist ebenfalls `None`. Ein Server, der die
        Verbindung annimmt und dann schweigt, haelt damit einen uwsgi-Prozess -- und es gibt vier.
        Fuer den getakteten Versender (Plan 11.7) waere es schlimmer: er sperrt sich selbst, ein
        Lauf ohne Ende haelt die Sperre und dann geht gar keine Mail mehr raus.
        """
        from django.conf import settings as django_settings

        assert django_settings.EMAIL_TIMEOUT is not None
        assert 0 < django_settings.EMAIL_TIMEOUT <= 60
