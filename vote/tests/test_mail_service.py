"""Tests für vote/services/mail.py -- vor allem: der Wortlaut der Mails.

Die Texte lagen bis 3.4 als `%`-formatierte Strings in `demockrazy/settings.py` und sind jetzt
Django-Templates. Das darf am Wortlaut **nichts** geändert haben (Plan-Regel 3/6: keine stillen
Änderungen an Mail-Texten). Die Erwartungswerte unten sind die Settings-Strings von vor dem Umbau,
hier absichtlich als Literale ausgeschrieben: damit hängt der Test weder an den Settings noch an
den Templates und schlägt an, wenn sich eine der beiden Seiten bewegt.
"""

import pytest

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
