"""Tests für vote/views.py gegen das in Phase 0 protokollierte Verhalten."""

import pytest
from django.urls import reverse

from vote.models import Choice, Poll, Token

from .conftest import CREATOR_MAIL, creator_message, voter_tokens

#: Eine Eingabe, die genau an einer Stelle kaputt ist -- der Rest muss die Fehlerseite überleben.
INVALID_PAYLOAD = {
    "title": "Wiedervorlage",
    "type": "simple_choice",
    "description": "Wollen wir das?",
    "choices": "Ja\nNein",
    "creator_mail": CREATOR_MAIL,
    "voter_mails": "gueltig@example.org\nKAPUTT",
}


class TestUrls:
    """Es sind Mails mit ?token=-Links auf bestehende Umfragen unterwegs.

    Diese Pfade dürfen sich beim Modernisieren nicht ändern (Plan-Regel 4).
    """

    def test_url_shapes(self):
        assert reverse("vote:index") == "/vote/"
        assert reverse("vote:create") == "/vote/create"
        assert reverse("vote:polls:poll", args=("abc",)) == "/vote/abc/"
        assert reverse("vote:polls:vote", args=("abc",)) == "/vote/abc/vote"
        assert reverse("vote:polls:success", args=("abc",)) == "/vote/abc/success"
        assert reverse("vote:polls:manage", args=("abc",)) == "/vote/abc/manage"
        assert reverse("vote:polls:result", args=("abc",)) == "/vote/abc/results"

    def test_root_redirects_to_vote(self, client):
        response = client.get("/")
        assert response.status_code == 302
        assert response.headers["Location"] == "vote/"


class TestIndex:
    def test_renders_form(self, client):
        response = client.get("/vote/")
        assert response.status_code == 200
        assert b'name="voter_mails"' in response.content


@pytest.mark.django_db
class TestCreate:
    def test_creates_poll_with_choices_and_tokens(self, create_poll):
        poll, tokens = create_poll(voters=("a@example.org", "b@example.org"))
        assert poll.question_text == "Wollen wir das?"
        assert poll.type == "simple_choice"
        assert poll.is_active is True
        assert poll.num_tokens == 2
        assert poll.token_set.count() == 2
        assert len(tokens) == 2
        assert list(poll.choice_set.values_list("choice_text", flat=True)) == ["Ja", "Nein"]

    def test_choices_are_trimmed_and_blank_lines_dropped(self, create_poll):
        poll, _ = create_poll(choices="Ja\nNein\n\n  Vielleicht  \n")
        assert list(poll.choice_set.values_list("choice_text", flat=True)) == [
            "Ja",
            "Nein",
            "Vielleicht",
        ]

    def test_blank_recipient_lines_are_ignored(self, create_poll):
        poll, tokens = create_poll(voters=("a@example.org", "", "  ", "b@example.org"))
        assert poll.num_tokens == 2
        assert len(tokens) == 2

    def test_sends_one_mail_per_voter_plus_creator(self, create_poll, mailoutbox):
        create_poll(voters=("a@example.org", "b@example.org"))
        assert len(mailoutbox) == 3
        assert [m.to for m in mailoutbox] == [[CREATOR_MAIL], ["a@example.org"], ["b@example.org"]]

    def test_voter_mail_contains_working_token_link(self, create_poll, mailoutbox):
        poll, tokens = create_poll(voters=("a@example.org",))
        message = mailoutbox[-1]
        assert poll.title in message.subject
        assert f"/vote/{poll.identifier}/?token={tokens[0]}" in message.body
        assert Token.objects.filter(token_string=tokens[0]).exists()

    def test_creator_mail_contains_manage_url_and_token(self, create_poll, mailoutbox):
        poll, _ = create_poll()
        message = creator_message(mailoutbox)
        assert poll.title in message.subject
        assert f"/vote/{poll.identifier}/manage" in message.body
        assert poll.creator_token in message.body

    def test_each_voter_gets_a_distinct_token(self, create_poll):
        _, tokens = create_poll(voters=("a@example.org", "b@example.org", "c@example.org"))
        assert len(set(tokens)) == 3

    def test_no_mails_when_sending_is_disabled(
        self, client, mailoutbox, settings, django_capture_on_commit_callbacks
    ):
        settings.VOTE_SEND_MAILS = False
        # Mit execute=True, sonst würde der Test auch bestehen, wenn der Versand nur nie läuft.
        with django_capture_on_commit_callbacks(execute=True):
            client.post(
                "/vote/create",
                {
                    "title": "Ohne Mailversand",
                    "type": "simple_choice",
                    "description": "?",
                    "choices": "Ja",
                    "creator_mail": CREATOR_MAIL,
                    "voter_mails": "a@example.org",
                },
            )
        assert Poll.objects.filter(title="Ohne Mailversand").exists()
        assert mailoutbox == []

    def test_mails_go_out_only_after_the_commit(
        self, client, mailoutbox, django_capture_on_commit_callbacks
    ):
        """B7: solange die Transaktion offen ist, darf keine Mail draußen sein.

        Sonst hinterlässt ein Rollback Wähler mit einem Token-Link, den es in der Datenbank nie
        gegeben hat -- und ein hängender SMTP-Server hält eine Schreibtransaktion offen.
        """
        with django_capture_on_commit_callbacks(execute=False) as callbacks:
            client.post(
                "/vote/create",
                {
                    "title": "Nach dem Commit",
                    "type": "simple_choice",
                    "description": "?",
                    "choices": "Ja",
                    "creator_mail": CREATOR_MAIL,
                    "voter_mails": "a@example.org",
                },
            )
            assert mailoutbox == [], "vor dem Commit darf nichts verschickt sein"
        assert len(callbacks) == 1, "der Versand soll an genau einem on_commit-Callback hängen"
        callbacks[0]()
        assert [m.to for m in mailoutbox] == [[CREATOR_MAIL], ["a@example.org"]]

    @pytest.mark.django_db(transaction=True)
    def test_a_real_commit_sends_without_help(self, client, mailoutbox):
        """Gegenprobe zum Test oben: hier committet die Transaktion wirklich.

        Die übrige Suite führt die on_commit-Callbacks von Hand aus. Dieser Test ist der Beleg,
        dass der Versand auch ohne diese Hilfe läuft -- also im Betrieb.
        """
        client.post(
            "/vote/create",
            {
                "title": "Echter Commit",
                "type": "simple_choice",
                "description": "?",
                "choices": "Ja",
                "creator_mail": CREATOR_MAIL,
                "voter_mails": "a@example.org",
            },
        )
        assert [m.to for m in mailoutbox] == [[CREATOR_MAIL], ["a@example.org"]]

    def test_multiple_choice_poll(self, create_poll):
        poll, _ = create_poll(poll_type="multiple_choice", choices="A\nB\nC")
        assert poll.type == "multiple_choice"
        assert poll.choice_set.count() == 3


@pytest.mark.django_db
class TestCreateFormErrors:
    """Der Fehlerpfad von `create()`, seit es über `PollCreateForm` läuft (Plan 3.2)."""

    def test_get_shows_the_form(self, client):
        response = client.get("/vote/create")
        assert response.status_code == 200
        assert b'name="voter_mails"' in response.content

    def test_invalid_input_renders_the_form_again(self, client):
        response = client.post("/vote/create", INVALID_PAYLOAD)
        assert response.status_code == 200
        assert response.context["form"].errors

    def test_invalid_input_creates_nothing(self, client):
        client.post("/vote/create", INVALID_PAYLOAD)
        assert not Poll.objects.exists()
        assert not Choice.objects.exists()
        assert not Token.objects.exists()

    def test_invalid_input_sends_no_mail(
        self, client, mailoutbox, django_capture_on_commit_callbacks
    ):
        """Auch nicht an den Ersteller -- sonst wäre eine Tippfehler-Schleife ein Mailversender."""
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            client.post("/vote/create", INVALID_PAYLOAD)
        assert callbacks == [], "ein ungültiges Formular soll keinen Versand vormerken"
        assert mailoutbox == []

    def test_the_entered_values_survive_an_error(self, client):
        """Wer 200 Adressen einfügt, soll sie nach einem Tippfehler nicht neu eintippen müssen."""
        response = client.post("/vote/create", INVALID_PAYLOAD)
        content = response.content.decode()
        assert "Wiedervorlage" in content
        assert "gueltig@example.org" in content
        assert "Ja\nNein" in content

    def test_the_selected_poll_type_survives_an_error(self, client):
        response = client.post("/vote/create", INVALID_PAYLOAD | {"type": "multiple_choice"})
        content = response.content.decode()
        assert 'value="multiple_choice" selected' in content

    def test_the_error_message_names_the_broken_address(self, client):
        response = client.post("/vote/create", INVALID_PAYLOAD)
        assert "KAPUTT" in response.content.decode()


@pytest.mark.django_db
class TestPollPage:
    def test_shows_poll_and_token(self, client, create_poll):
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.status_code == 200
        assert response.context["token"] == tokens[0]
        assert response.context["error_message"] is None

    def test_reports_unknown_token(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": "gibtsnicht"})
        assert response.status_code == 200
        assert (
            response.context["error_message"] == "This token is invalid. Maybe you voted already?"
        )

    def test_token_counters(self, client, create_poll):
        poll, tokens = create_poll(voters=("a@example.org", "b@example.org", "c@example.org"))
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.context["amount_tokens_total"] == 3
        assert response.context["amount_remaining_tokens"] == 3
        assert response.context["amount_redeemed_tokens"] == 0

    def test_unknown_poll_is_404(self, client):
        assert client.get("/vote/gibtsnicht/").status_code == 404

    def test_closed_poll_redirects_to_results(self, client, create_poll):
        poll, _ = create_poll()
        poll.is_active = False
        poll.save()
        response = client.get(f"/vote/{poll.identifier}/")
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"


@pytest.mark.django_db
class TestVoteSimpleChoice:
    def test_counts_vote_and_burns_token(self, client, create_poll):
        poll, tokens = create_poll()
        choice = poll.choice_set.first()
        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.id}
        )
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/success"
        choice.refresh_from_db()
        assert choice.votes == 1
        assert not Token.objects.filter(token_string=tokens[0]).exists()

    def test_poll_stays_open_while_tokens_remain(self, client, create_poll):
        poll, tokens = create_poll()
        client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[0], "choice": poll.choice_set.first().id},
        )
        poll.refresh_from_db()
        assert poll.is_active is True

    def test_last_token_closes_the_poll(self, client, create_poll):
        poll, tokens = create_poll()
        for token in tokens:
            client.post(
                f"/vote/{poll.identifier}/vote",
                {"token": token, "choice": poll.choice_set.first().id},
            )
        poll.refresh_from_db()
        assert poll.is_active is False
        assert poll.token_set.count() == 0
        assert poll.get_amount_used_unused() == (2, 0, 2)

    def test_missing_choice_keeps_token(self, client, create_poll):
        poll, tokens = create_poll()
        response = client.post(f"/vote/{poll.identifier}/vote", {"token": tokens[0]})
        assert response.status_code == 200
        assert response.context["error_message"] == "Please fill out all fields."
        assert Token.objects.filter(token_string=tokens[0]).exists()
        assert poll.choice_set.first().votes == 0

    def test_unknown_choice_id_keeps_token(self, client, create_poll):
        poll, tokens = create_poll()
        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": 999999}
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "You didn't select a choice."
        assert Token.objects.filter(token_string=tokens[0]).exists()

    @pytest.mark.parametrize("value", ["abc", "", "1; DROP TABLE", "-1"])
    def test_unusable_choice_id_keeps_token(self, client, create_poll, value):
        """B15: ein nicht-numerischer Wert lief in einen ValueError aus dem pk-Lookup, also 500."""
        poll, tokens = create_poll()
        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": value}
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "You didn't select a choice."
        assert Token.objects.filter(token_string=tokens[0]).exists()
        assert poll.choice_set.first().votes == 0

    def test_get_does_not_crash(self, client, create_poll):
        """Ohne POST-Daten gibt es keinen Token -- das ist eine Fehlermeldung, kein 500."""
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/vote")
        assert response.status_code == 200
        assert response.context["error_message"] == "invalid token."

    def test_unknown_token_is_rejected(self, client, create_poll):
        poll, _ = create_poll()
        response = client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": "gibtsnicht", "choice": poll.choice_set.first().id},
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "invalid token."

    def test_token_from_another_poll_is_rejected(self, client, create_poll):
        first, _ = create_poll(title="Erste")
        _, other_tokens = create_poll(title="Zweite")
        response = client.post(
            f"/vote/{first.identifier}/vote",
            {"token": other_tokens[0], "choice": first.choice_set.first().id},
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "invalid token."
        assert first.choice_set.first().votes == 0
        assert Token.objects.filter(token_string=other_tokens[0]).exists()

    def test_voting_on_closed_poll_redirects(self, client, create_poll):
        poll, tokens = create_poll()
        poll.is_active = False
        poll.save()
        response = client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[0], "choice": poll.choice_set.first().id},
        )
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"
        assert poll.choice_set.first().votes == 0


@pytest.mark.django_db
class TestVoteMultipleChoice:
    def test_counts_only_the_yes_answers(self, client, create_poll):
        poll, tokens = create_poll(
            poll_type="multiple_choice", choices="A\nB\nC", voters=("a@example.org",)
        )
        choices = list(poll.choice_set.all())
        client.post(
            f"/vote/{poll.identifier}/vote",
            {
                "token": tokens[0],
                f"choice{choices[0].id}": "yes",
                f"choice{choices[1].id}": "no",
                f"choice{choices[2].id}": "yes",
            },
        )
        votes = [Choice.objects.get(pk=c.pk).votes for c in choices]
        assert votes == [1, 0, 1]

    def test_incomplete_answer_rolls_everything_back(self, client, create_poll):
        """Wichtig: die Teilstimme darf nicht gezählt werden und der Token muss erhalten bleiben."""
        poll, tokens = create_poll(
            poll_type="multiple_choice", choices="A\nB", voters=("a@example.org",)
        )
        choices = list(poll.choice_set.all())
        response = client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[0], f"choice{choices[0].id}": "yes"},
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "Please fill out all fields."
        assert [Choice.objects.get(pk=c.pk).votes for c in choices] == [0, 0]
        assert Token.objects.filter(token_string=tokens[0]).exists()
        poll.refresh_from_db()
        assert poll.is_active is True


@pytest.mark.django_db
class TestManage:
    def test_wrong_token_does_not_close(self, client, create_poll):
        poll, _ = create_poll()
        response = client.post(f"/vote/{poll.identifier}/manage", {"token": "falsch"})
        assert response.status_code == 200
        assert response.context["error_message"] == "Wrong management token"
        poll.refresh_from_db()
        assert poll.is_active is True

    def test_creator_token_closes_the_poll(self, client, create_poll):
        poll, _ = create_poll()
        response = client.post(f"/vote/{poll.identifier}/manage", {"token": poll.creator_token})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"
        poll.refresh_from_db()
        assert poll.is_active is False

    def test_unused_tokens_survive_early_close_and_count_as_abstentions(self, client, create_poll):
        poll, _ = create_poll()
        client.post(f"/vote/{poll.identifier}/manage", {"token": poll.creator_token})
        poll.refresh_from_db()
        assert poll.token_set.count() == 2
        assert poll.get_amount_used_unused() == (0, 2, 2)

    def test_get_shows_the_form(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/manage")
        assert response.status_code == 200
        assert response.context["error_message"] is None

    def test_closed_poll_redirects(self, client, create_poll):
        poll, _ = create_poll()
        poll.is_active = False
        poll.save()
        response = client.get(f"/vote/{poll.identifier}/manage")
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"


@pytest.mark.django_db
class TestResults:
    def test_open_poll_redirects_to_the_poll(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/results")
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/"

    def test_shows_counts_after_close(self, client, create_poll):
        poll, tokens = create_poll()
        choice = poll.choice_set.first()
        for token in tokens:
            client.post(f"/vote/{poll.identifier}/vote", {"token": token, "choice": choice.id})
        response = client.get(f"/vote/{poll.identifier}/results")
        assert response.status_code == 200
        assert response.context["amount_redeemed_tokens"] == 2
        assert response.context["amount_remaining_tokens"] == 0
        assert str(choice.choice_text).encode() in response.content

    def test_success_page(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/success")
        assert response.status_code == 200
        assert poll.title.encode() in response.content


@pytest.mark.django_db
class TestAnonymity:
    """Das Kernversprechen: nach der Stimmabgabe gibt es keine Verbindung Wähler -> Stimme."""

    def test_no_mail_address_is_stored_anywhere(self, create_poll):
        create_poll(voters=("geheim@example.org",))
        for poll in Poll.objects.all():
            assert "geheim@example.org" not in str(poll.__dict__)
        for token in Token.objects.all():
            assert "geheim@example.org" not in str(token.__dict__)

    def test_token_is_gone_after_voting(self, client, create_poll):
        poll, tokens = create_poll(voters=("a@example.org",))
        client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[0], "choice": poll.choice_set.first().id},
        )
        assert Token.objects.filter(token_string=tokens[0]).count() == 0

    def test_token_cannot_be_reused(self, client, create_poll):
        poll, tokens = create_poll()
        choice = poll.choice_set.first()
        client.post(f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.id})
        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.id}
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "invalid token."
        choice.refresh_from_db()
        assert choice.votes == 1


@pytest.mark.django_db
class TestMailHelpers:
    """Sichert die Test-Helfer selbst ab, damit ein leeres Postfach nicht als Erfolg durchgeht."""

    def test_voter_tokens_skips_the_creator_mail(self, create_poll, mailoutbox):
        create_poll(voters=("a@example.org", "b@example.org"))
        assert len(voter_tokens(mailoutbox)) == 2
