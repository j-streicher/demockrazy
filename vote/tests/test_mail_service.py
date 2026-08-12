"""Tests für vote/services/mail.py -- vor allem: der Wortlaut der Mails.

Die Texte lagen bis 3.4 als `%`-formatierte Strings in `demockrazy/settings.py` und sind jetzt
Django-Templates. Das darf am Wortlaut **nichts** geändert haben (Plan-Regel 3/6: keine stillen
Änderungen an Mail-Texten). Die Erwartungswerte unten sind die Settings-Strings von vor dem Umbau,
hier absichtlich als Literale ausgeschrieben: damit hängt der Test weder an den Settings noch an
den Templates und schlägt an, wenn sich eine der beiden Seiten bewegt.
"""

from smtplib import SMTPException, SMTPRecipientsRefused, SMTPServerDisconnected
from typing import ClassVar

import pytest
from django.core.mail.backends.base import BaseEmailBackend

from vote.models import OutgoingMail, Poll, Token
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

    def test_each_voter_gets_exactly_one_of_the_tokens(self, poll):
        """Jeder genau einen, keiner zweimal, keiner übrig -- aber **nicht** in fester Reihenfolge.

        Vorher stand hier `"?token=t0" in links[0]`, also genau die Paarung, die R1-2 aufgelöst hat.
        Geprüft ist jetzt die Eigenschaft, auf die es ankommt: eine Bijektion.
        """
        tokens = [Token.objects.create(poll=poll, token_string=f"t{i}") for i in range(5)]
        voters = [f"w{i}@example.org" for i in range(5)]
        messages = mail.poll_created_messages(poll, "admin@example.org", voters, tokens)

        vergeben = []
        for _, body, recipient in messages[1:]:
            treffer = [
                token.token_string for token in tokens if f"?token={token.token_string}" in body
            ]
            assert len(treffer) == 1, (recipient, treffer)
            vergeben.append(treffer[0])
        assert sorted(vergeben) == sorted(token.token_string for token in tokens)

    def test_the_pairing_does_not_follow_the_recipient_order(self, poll):
        """R1-2: die Token-`id`s liefen parallel zur Empfängerliste, und die `id`s bleiben.

        Gemessen war es so: Adresse 1 bekam Token 1 ... Adresse 5 bekam Token 5. Nach dem Versand
        steht keine Adresse mehr in der Datenbank, die `id`-Reihenfolge aber schon -- wer die Liste
        kennt und die Datenbank lesen kann, las an den verbliebenen `id`s ab, *wer* schon abgestimmt
        hat. Die Stimme selbst war nie betroffen.

        Zehn Umfragen mit je sechs Empfängern: dass **alle** zehn zufällig die Identität treffen,
        hat die Wahrscheinlichkeit (1/720)^10.
        """
        voters = [f"w{i}@example.org" for i in range(6)]
        unveraendert = 0
        for runde in range(10):
            tokens = [
                Token.objects.create(poll=poll, token_string=f"r{runde}t{i}") for i in range(6)
            ]
            messages = mail.poll_created_messages(poll, "admin@example.org", voters, tokens)
            reihenfolge = [
                next(token.pk for token in tokens if f"?token={token.token_string}" in body)
                for _, body, _ in messages[1:]
            ]
            if reihenfolge == sorted(reihenfolge):
                unveraendert += 1
        assert unveraendert < 10, "die Paarung folgt weiterhin der Eingabereihenfolge"

    def test_mismatched_token_count_is_an_error(self, poll):
        """Ein Wähler ohne Token (oder umgekehrt) ist ein Programmierfehler, kein stiller Sonderfall."""
        tokens = [Token.objects.create(poll=poll, token_string="t0")]
        with pytest.raises(ValueError):
            mail.poll_created_messages(poll, "admin@example.org", ["a@x.org", "b@x.org"], tokens)


class CountingBackend(BaseEmailBackend):
    """Ein Mail-Backend, das protokolliert, *wann* eine Verbindung entsteht, und Fehler nachstellt.

    Es gibt kein Django-Backend, das das zeigt: `locmem` überspringt Verbindungen ganz, `smtp`
    bräuchte einen Server. Die Semantik von `open()`/`close()` ist deshalb der des SMTP-Backends
    nachgebildet -- offen bleibt offen, ein zweites `open()` ist ein No-op.

    Gesteuert über Klassenattribute, weil Django das Backend selbst instanziiert und man ihm keine
    Argumente mitgeben kann.
    """

    #: Protokoll in Reihenfolge: "open", "close" und die Empfängeradressen.
    log: ClassVar[list] = []
    #: Empfänger, die der Server mit 450 vorläufig ablehnt -- die Form der Drosselung.
    refuse_temporarily: ClassVar[tuple] = ()
    #: Empfänger, die der Server mit 550 dauerhaft ablehnt.
    refuse_permanently: ClassVar[tuple] = ()
    #: Server gar nicht erreichbar: `open()` bricht weg.
    unreachable: ClassVar[bool] = False
    #: Ob `close()` beim Aufräumen wirft -- was das echte SMTP-Backend beim QUIT kann.
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
            raise SMTPServerDisconnected("Verbindung weg")
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
            # `message()` baut die Nachricht wirklich -- damit prüft dieses Double dieselben Header
            # wie ein echtes Backend (Djangos locmem-Backend tut es aus demselben Grund). Ohne den
            # Aufruf nahm es Nachrichten an, die kein Mailserver je gesehen hätte: der
            # `BadHeaderError` aus R5-1 entsteht genau hier.
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
    """Nimmt die Pausen auf statt zu warten. Ohne das dauerte die Suite Minuten."""
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
    """Der getaktete Versender (Plan §11.7). Vorher hieß das `deliver()` und verschickte sofort."""

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
        """Vorher baute jeder send_mail()-Aufruf seine eigene: 101 Mails = 101 Verbindungen.

        Die Verbindung endet an der Batchgrenze, damit die Pause nicht in einer offenen Verbindung
        verbracht wird -- innerhalb eines Batches bleibt es bei einer für alle Nachrichten.
        """
        enqueue(20)
        mail.send_pending(batch_size=5, pause=0)
        assert counting_backend.log.count("open") == 4
        assert counting_backend.log.count("close") == 4
        assert len(counting_backend.recipients()) == 20

    def test_the_pause_lies_between_the_batches(self, counting_backend, recorded_sleep):
        """Nicht vor dem ersten Batch (sonst wartet jeder Lauf umsonst) und nicht nach dem letzten
        (sonst hält der Command seine Sperre länger, als er arbeitet)."""
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
        """Ein 5xx betrifft genau diese Adresse -- die übrigen des Batches gehen raus."""
        counting_backend.refuse_permanently = ("a1@example.org",)
        enqueue(3)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == ["a0@example.org", "a2@example.org"]
        assert OutgoingMail.objects.count() == 0, "auch die abgelehnte Zeile ist weg"
        assert summary["sent"] == 2
        assert summary["given_up"] == 1

    def test_the_log_names_the_smtp_code_but_no_address(self, counting_backend, caplog):
        """R6-1: die Logzeile nannte keinen Grund -- und der Kommentar behauptete das Gegenteil.

        Gemessen war es genau eine Zeile: „Eine Umfrage-Mail wurde dauerhaft abgelehnt und
        verworfen", ohne `exc_info`, ohne Code. Damit war aus dem Journal nicht zu entscheiden, ob
        eine Adresse falsch war oder der Server zickt. Die Adresse gehört weiter **nicht** hinein
        (F8), ein SMTP-Code ist eine Zahl.
        """
        counting_backend.refuse_permanently = ("a1@example.org",)
        enqueue(3)
        with caplog.at_level("WARNING"):
            mail.send_pending(pause=0)

        assert "550" in caplog.text
        assert "a1@example.org" not in caplog.text

    def test_a_transient_rejection_stops_the_run(self, counting_backend):
        """Der `450` der Drosselung. Weitermachen hieße, die restlichen 29 gegen dieselbe Wand
        zu fahren -- der nächste Timer-Aufruf trifft ein zurückgesetztes Zeitfenster an."""
        counting_backend.refuse_temporarily = ("a1@example.org",)
        enqueue(4)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == ["a0@example.org"]
        assert summary["sent"] == 1
        assert summary["remaining"] == 3, "die abgelehnte Zeile und die zwei dahinter liegen noch"
        assert OutgoingMail.objects.get(recipient="a1@example.org").attempts == 1

    def test_a_transient_rejection_is_given_up_eventually(self, counting_backend):
        counting_backend.refuse_temporarily = ("a0@example.org",)
        enqueue(1)
        for _ in range(mail.MAX_ATTEMPTS):
            mail.send_pending(pause=0)
        assert OutgoingMail.objects.count() == 0, "irgendwann wird aufgegeben"

    def test_an_unreachable_server_costs_no_attempt(self, counting_backend):
        """Sonst würde ein einstündiger Ausfall die Einladungen der Reihe nach wegwerfen.

        Der Server hat über *diese* Nachricht nichts gesagt -- also kein Urteil über sie.
        """
        counting_backend.unreachable = True
        enqueue(3)
        summary = mail.send_pending(pause=0)
        assert counting_backend.recipients() == []
        assert summary == {"sent": 0, "given_up": 0, "batches": 1, "remaining": 3}
        assert {row.attempts for row in OutgoingMail.objects.all()} == {0}

    def test_a_failure_while_closing_does_not_escape(self, counting_backend):
        """Die Mails dieses Batches sind raus und ihre Zeilen gelöscht -- ein QUIT, das schiefgeht,
        darf daraus keinen Abbruch machen."""
        counting_backend.fail_on_close = True
        enqueue(2)
        summary = mail.send_pending(pause=0)
        assert summary["sent"] == 2
        assert OutgoingMail.objects.count() == 0

    def test_nothing_is_sent_when_sending_is_disabled(self, counting_backend, settings, capsys):
        """Ohne Versand entsteht keine Verbindung. Die Zeilen verschwinden trotzdem -- sonst liefe
        der Lauf endlos über dieselbe Warteschlange."""
        settings.VOTE_SEND_MAILS = False
        enqueue(2)
        mail.send_pending(pause=0)
        assert counting_backend.log == []
        assert OutgoingMail.objects.count() == 0
        assert "Betreff 0" in capsys.readouterr().out

    def test_the_defaults_come_from_the_settings(self, counting_backend, recorded_sleep, settings):
        """Die zwei Zahlen sind vom User vorgegeben und müssen konfigurierbar bleiben."""
        sleep, calls = recorded_sleep
        settings.VOTE_MAIL_BATCH_SIZE = 2
        settings.VOTE_MAIL_BATCH_PAUSE = 7
        enqueue(4)
        assert mail.send_pending(sleep=sleep)["batches"] == 2
        assert calls == [7]

    def test_the_pacing_values_are_the_ones_the_user_asked_for(self):
        """R10-3: die Taktung war konfigurierbar, aber ihre *Werte* nagelte nichts fest.

        30er Batches mit 2 s Pause sind vom User vorgegeben, und Produktion benutzt genau diese
        Defaults -- die Tests darüber übergeben `batch_size`/`pause` aber immer ausdrücklich, also
        blieb eine Änderung an den Defaults unbemerkt (gemessen per Mutation: 30 -> 1000 fiel der
        ganzen Suite nicht auf).
        """
        from django.conf import settings as django_settings

        assert (django_settings.VOTE_MAIL_BATCH_SIZE, django_settings.VOTE_MAIL_BATCH_PAUSE) == (
            30,
            2,
        ), (
            "Vom User vorgegeben (Plan §11.7). Wenn das absichtlich anders sein soll, gehört die "
            "Begründung in die Notizen -- und wenn dieser Test lokal fehlschlägt, ist vermutlich "
            "DEMOCKRAZY_MAIL_BATCH_SIZE/_PAUSE in der Umgebung gesetzt."
        )

    def test_a_silent_mail_server_cannot_block_forever(self):
        """`EMAIL_TIMEOUT` muss endlich sein. Djangos Default ist `None`, also unbegrenzt.

        Nachgesehen statt vermutet: bei `None` gibt das SMTP-Backend `timeout` nicht an `smtplib`
        weiter, das nimmt den Socket-Default, und der ist ebenfalls `None`. Ein Server, der die
        Verbindung annimmt und dann schweigt, haelt damit einen uwsgi-Prozess -- und es gibt vier.
        Fuer den getakteten Versender ist es schlimmer: er sperrt sich selbst, ein Lauf ohne Ende
        haelt die Sperre und dann geht gar keine Mail mehr raus.
        """
        from django.conf import settings as django_settings

        assert django_settings.EMAIL_TIMEOUT is not None
        assert 0 < django_settings.EMAIL_TIMEOUT <= 60


@pytest.mark.django_db
class TestUnsendableRowDoesNotStopTheRun:
    """R5-1: eine Zeile, die sich nicht zu einer Nachricht bauen lässt, kostet nur sich selbst.

    Der Befund: ein Zeilenumbruch im Umfragetitel landete im Betreff, Djangos
    `forbid_multi_line_headers` warf einen `BadHeaderError` -- eine `ValueError`-Unterklasse, die
    weder von `SMTPException` noch von `OSError` gedeckt ist. Sie flog bis in den
    Management-Command, und weil die Zeile vorn in der Warteschlange liegen blieb, starb jeder
    weitere Timer-Aufruf an derselben Stelle: kein Versand mehr, für keine Umfrage.
    """

    def test_the_run_survives_it_and_the_others_go_out(self, counting_backend):
        OutgoingMail.objects.create(
            recipient="erste@example.org", subject="Poll 'a\nBcc: x@y.z' created", body="hi"
        )
        OutgoingMail.objects.create(recipient="zweite@example.org", subject="harmlos", body="hi")

        summary = mail.send_pending(pause=0)

        assert counting_backend.recipients() == ["zweite@example.org"]
        assert summary == {"sent": 1, "given_up": 1, "batches": 1, "remaining": 0}
        assert OutgoingMail.objects.count() == 0, "die kaputte Zeile muss verschwinden"

    def test_a_poll_created_through_the_form_cannot_produce_such_a_row(self, client):
        """Die andere Hälfte der Behebung: das Formular lässt den Umbruch nicht mehr durch."""
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
    """R5-2: die Schleife endet auch, wenn ein Durchlauf nichts bewegt.

    Aufgefallen ist das unbeabsichtigt: eine Mutation, die den Zweig für „Server nicht erreichbar"
    entfernte -- also eine Zeile, die weder löscht noch abbricht --, schickte die Testsuite in eine
    Endlosschleife, die nach neun Minuten noch lief, **ohne** einen fehlschlagenden Test. In
    Produktion wäre das schlimmer als ein Absturz: der Lauf hält die `flock`, also geht danach
    überhaupt keine Mail mehr raus, und von außen sieht „hängt" aus wie „arbeitet noch".
    """

    def test_a_batch_that_changes_nothing_ends_the_run(self, monkeypatch, caplog):
        enqueue(3)
        monkeypatch.setattr(mail, "_send_batch", lambda rows, summary: False)

        summary = mail.send_pending(pause=0)

        assert summary == {"sent": 0, "given_up": 0, "batches": 1, "remaining": 3}
        assert "kommt nicht voran" in caplog.text

    def test_the_guard_does_not_trip_on_a_normal_multi_batch_run(self, counting_backend):
        """Gegenprobe: solange etwas verschwindet, läuft die Warteschlange normal leer."""
        enqueue(7)
        summary = mail.send_pending(batch_size=2, pause=0)
        assert summary == {"sent": 7, "given_up": 0, "batches": 4, "remaining": 0}
