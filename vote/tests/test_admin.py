"""R2-1: was ein Staff-Konto über `/admin/` **nicht** kann.

Der Befund war nicht theoretisch: `/admin/` ist seit 2016 geroutet, alle drei Modelle waren ohne
Einschränkung registriert, und der User hat bestätigt, dass es in Produktion ein Staff-Konto gibt.
Ein Passwort öffnete damit den einzigen Weg im System, der Stimmzahlen unmittelbar ändern und jeden
Wähler-Token lesen konnte.

Die Tests fahren gegen die echte Admin-Oberfläche, nicht gegen die `ModelAdmin`-Attribute: geprüft
werden soll die Wirkung. `admin_client` (pytest-django) legt einen Superuser an und meldet ihn an --
also der stärkste Fall, nicht der schwächste.
"""

import pytest

from vote.models import Choice, Poll, Token


@pytest.fixture
def poll(db):
    poll = Poll.objects.create(title="Kantinenwahl", question_text="Was essen wir?", num_tokens=2)
    Choice.objects.create(poll=poll, choice_text="Pizza", votes=7)
    Token.objects.create(poll=poll)
    return poll


@pytest.mark.django_db
class TestVoteCountsCannotBeEdited:
    def test_the_change_form_has_no_input_for_votes(self, admin_client, poll):
        choice = poll.choice_set.get()
        content = admin_client.get(f"/admin/vote/choice/{choice.pk}/change/").content.decode()
        assert 'name="votes"' not in content
        # Angezeigt wird die Zahl weiterhin -- nur eben nicht als Eingabefeld.
        assert '<div class="readonly">7</div>' in content

    def test_a_posted_vote_count_is_ignored(self, admin_client, poll):
        """Der eigentliche Beweis: auch ein Formular, das das Feld mitschickt, ändert nichts."""
        choice = poll.choice_set.get()
        response = admin_client.post(
            f"/admin/vote/choice/{choice.pk}/change/",
            {"poll": poll.pk, "choice_text": "Pizza", "votes": "9999"},
        )
        choice.refresh_from_db()
        assert response.status_code in (200, 302)
        assert choice.votes == 7, "Stimmzahl über das Admin-Formular verändert"

    def test_adding_a_choice_starts_at_zero(self, admin_client, poll):
        admin_client.post(
            "/admin/vote/choice/add/",
            {"poll": poll.pk, "choice_text": "Pasta", "votes": "500"},
        )
        neu = Choice.objects.get(choice_text="Pasta")
        assert neu.votes == 0


@pytest.mark.django_db
class TestTokensCannotBeRead:
    def test_the_voter_token_appears_neither_in_the_list_nor_in_the_form(self, admin_client, poll):
        token = poll.token_set.get()
        liste = admin_client.get("/admin/vote/token/").content.decode()
        formular = admin_client.get(f"/admin/vote/token/{token.pk}/change/").content.decode()
        for seite in (liste, formular):
            assert token.token_string not in seite
            assert 'name="token_string"' not in seite

    def test_the_creator_token_is_not_shown_either(self, admin_client, poll):
        """Er schließt die Umfrage vorzeitig -- ein Geheimnis, das nicht auf eine Seite gehört."""
        liste = admin_client.get("/admin/vote/poll/").content.decode()
        formular = admin_client.get(f"/admin/vote/poll/{poll.pk}/change/").content.decode()
        for seite in (liste, formular):
            assert poll.creator_token not in seite
            assert 'name="creator_token"' not in seite

    def test_the_identifier_cannot_be_changed(self, admin_client, poll):
        """Es sind Mails mit Links auf diese Kennung unterwegs (Arbeitsregel 5).

        Der Statuscode gehört zur Prüfung: ohne ihn besteht dieser Test auch mit der alten
        Registrierung, weil der POST dort an einem *anderen* fehlenden Pflichtfeld scheitert und die
        Kennung deshalb ebenfalls stehen bleibt. Ein Test, der aus dem falschen Grund grün ist, ist
        Fehlerklasse K4 -- gemessen, indem die alte `admin.py` zurückgespielt wurde.
        """
        alt = poll.identifier
        formular = admin_client.get(f"/admin/vote/poll/{poll.pk}/change/").content.decode()
        assert 'name="identifier"' not in formular

        response = admin_client.post(
            f"/admin/vote/poll/{poll.pk}/change/",
            {
                "title": "Kantinenwahl",
                "type": "simple_choice",
                "question_text": "Was essen wir?",
                "num_tokens": 2,
                "identifier": "eineandere",
                "is_active": "on",
                "pub_date_0": "2026-08-04",
                "pub_date_1": "12:00:00",
            },
        )
        poll.refresh_from_db()
        assert response.status_code == 302, "der POST muss durchgehen, sonst prüft der Test nichts"
        assert poll.identifier == alt


@pytest.mark.django_db
class TestWhatStaysPossible:
    """Gegenprobe: die Oberfläche ist beschnitten, nicht abgeschaltet."""

    def test_a_poll_can_still_be_closed(self, admin_client, poll):
        admin_client.post(
            f"/admin/vote/poll/{poll.pk}/change/",
            {
                "title": "Kantinenwahl",
                "type": "simple_choice",
                "question_text": "Was essen wir?",
                "num_tokens": 2,
                "pub_date_0": "2026-08-04",
                "pub_date_1": "12:00:00",
            },
        )
        poll.refresh_from_db()
        assert poll.is_active is False, "das Häkchen fehlt im POST, also soll die Umfrage zu sein"

    def test_a_poll_can_still_be_deleted(self, admin_client, poll):
        admin_client.post(f"/admin/vote/poll/{poll.pk}/delete/", {"post": "yes"})
        assert not Poll.objects.filter(pk=poll.pk).exists()
        assert Token.objects.count() == 0, "die Tokens hängen per CASCADE daran"
