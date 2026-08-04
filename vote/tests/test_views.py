"""Tests für vote/views.py gegen das in Phase 0 protokollierte Verhalten."""

from typing import ClassVar

import pytest
from django.test import Client
from django.urls import Resolver404, resolve, reverse

from vote.models import Choice, OutgoingMail, Poll, Token
from vote.services import mail
from vote.views import TOKEN_COOKIE_NAME

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

    def test_identifier_route_matches_the_generated_alphabet(self):
        match = resolve("/vote/aZ09/")
        assert match.view_name == "vote:polls:poll"
        assert match.kwargs == {"poll_identifier": "aZ09"}

    @pytest.mark.parametrize("identifier", ["ab-c", "ab_c", "äbc"])
    def test_identifier_route_matches_nothing_beyond_it(self, identifier):
        """Gegenprobe zum eigenen Converter aus vote/urls.py.

        `mk_identifier()` zieht nur aus `ascii_letters + digits`. Djangos `slug`
        hätte `-` und `_` zusätzlich angenommen, also mehr als der alte
        `re_path`-Ausdruck -- das darf nicht bis zur View durchkommen.
        """
        with pytest.raises(Resolver404):
            resolve(f"/vote/{identifier}/")


class TestIndex:
    def test_renders_form(self, client):
        response = client.get("/vote/")
        assert response.status_code == 200
        assert b'name="voter_mails"' in response.content

    def test_clean_form_carries_no_aria_error_markup(self, client):
        """Gegenprobe zum Test unten: ohne Fehler behauptet das Formular keinen (Plan 4.5)."""
        content = client.get("/vote/").content
        assert b"aria-invalid" not in content
        assert b"aria-describedby" not in content

    @pytest.mark.django_db
    def test_field_error_is_announced_at_the_field(self, client):
        """Die Fehlerliste steht optisch beim Feld -- ein Screenreader braucht die Verknüpfung.

        `voter_mails` ist das kaputte Feld in INVALID_PAYLOAD, `title` das intakte daneben.
        """
        content = client.post("/vote/create", INVALID_PAYLOAD).content.decode()

        assert 'id="voter_mails-errors"' in content
        assert 'aria-describedby="voter_mails-errors"' in content
        assert 'aria-invalid="true"' in content
        assert 'aria-describedby="title-errors"' not in content


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

    def test_no_mails_when_sending_is_disabled(self, mailoutbox, settings, create_poll):
        settings.VOTE_SEND_MAILS = False
        create_poll(title="Ohne Mailversand", voters=("a@example.org",))
        assert Poll.objects.filter(title="Ohne Mailversand").exists()
        assert mailoutbox == []

    def test_multiple_choice_poll(self, create_poll):
        poll, _ = create_poll(poll_type="multiple_choice", choices="A\nB\nC")
        assert poll.type == "multiple_choice"
        assert poll.choice_set.count() == 3


@pytest.mark.django_db
class TestCreateQueuesMails:
    """`create()` reiht die Mails ein und verschickt selbst nichts (Plan §11.7).

    Das ist die neue Form der Zusage aus B7 („keine Mail, bevor die Tokens durabel sind"): sie hängt
    nicht mehr an einem `on_commit`-Callback, sondern daran, dass ein **anderer Prozess** verschickt
    und nur committete Zeilen sieht.
    """

    PAYLOAD: ClassVar[dict] = {
        "title": "Eingereiht",
        "type": "simple_choice",
        "description": "?",
        "choices": "Ja",
        "creator_mail": CREATOR_MAIL,
        "voter_mails": "a@example.org\nb@example.org",
    }

    def test_the_request_sends_nothing(self, client, mailoutbox):
        client.post("/vote/create", self.PAYLOAD)
        assert mailoutbox == [], "der Request selbst darf keine Mail verschicken"

    def test_one_queue_row_per_recipient_plus_the_creator(self, client):
        client.post("/vote/create", self.PAYLOAD)
        assert OutgoingMail.objects.count() == 3

    def test_the_creator_comes_first(self, client):
        client.post("/vote/create", self.PAYLOAD)
        recipients = list(OutgoingMail.objects.order_by("pk").values_list("recipient", flat=True))
        assert recipients == [CREATOR_MAIL, "a@example.org", "b@example.org"]

    def test_a_queue_row_does_not_name_its_poll(self, client):
        """F8: eine Zeile soll für sich nicht sagen, um welche Abstimmung es geht.

        Geprüft an den Feldern und nicht am Inhalt: ein Fremdschlüssel oder eine Kennungsspalte
        wäre genau das, was hier nicht entstehen darf. Der *Text* nennt den Titel natürlich -- er
        ist die Einladung.
        """
        client.post("/vote/create", self.PAYLOAD)
        columns = {field.name for field in OutgoingMail._meta.get_fields()}
        assert columns == {"id", "recipient", "subject", "body", "attempts"}
        assert not any(field.is_relation for field in OutgoingMail._meta.get_fields())

    def test_an_invalid_form_queues_nothing(self, client):
        client.post("/vote/create", {**self.PAYLOAD, "voter_mails": "KAPUTT"})
        assert OutgoingMail.objects.count() == 0

    def test_the_queue_survives_into_a_real_transaction(self, client, mailoutbox):
        """Gegenprobe mit echtem Commit: hier hilft kein Testmechanismus nach.

        Vorher stand hier die Gegenprobe für `on_commit` -- dass der Versand auch ohne das
        Ausführen der Callbacks von Hand läuft. Die Zusage ist jetzt eine andere: nach dem Commit
        liegen die Zeilen da, und erst ein separater Lauf verschickt sie.
        """
        client.post("/vote/create", self.PAYLOAD)
        assert OutgoingMail.objects.count() == 3
        assert mailoutbox == []
        mail.send_pending(pause=0)
        assert [message.to for message in mailoutbox] == [
            [CREATOR_MAIL],
            ["a@example.org"],
            ["b@example.org"],
        ]
        assert OutgoingMail.objects.count() == 0


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
    """`follow=True`, weil ein Token in der URL seit B9 erst umzieht und dann umleitet.

    Was dabei passiert, prüft `TestTokenLeavesTheUrl`; hier interessiert nur die Seite am Ende.
    """

    def test_shows_poll_and_token(self, client, create_poll):
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        assert response.status_code == 200
        assert response.context["token"] == tokens[0]
        assert response.context["error_message"] is None

    def test_reports_unknown_token(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": "gibtsnicht"}, follow=True)
        assert response.status_code == 200
        assert (
            response.context["error_message"] == "This token is invalid. Maybe you voted already?"
        )

    def test_token_counters(self, client, create_poll):
        poll, tokens = create_poll(voters=("a@example.org", "b@example.org", "c@example.org"))
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        assert response.context["amount_tokens_total"] == 3
        assert response.context["amount_remaining_tokens"] == 3
        assert response.context["amount_redeemed_tokens"] == 0

    def test_without_a_token_the_field_is_empty(self, client, create_poll):
        """Kein Token, kein Umzug, keine Fehlermeldung -- nur ein leeres Feld zum Abtippen."""
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/")
        assert response.status_code == 200
        assert response.context["token"] == ""
        assert response.context["error_message"] is None

    def test_unknown_poll_is_404(self, client):
        assert client.get("/vote/gibtsnicht/").status_code == 404

    def test_closed_poll_redirects_to_results(self, client, create_poll):
        poll, _ = create_poll()
        poll.is_active = False
        poll.save()
        response = client.get(f"/vote/{poll.identifier}/")
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"

    def test_closed_poll_redirects_to_results_even_with_a_token(self, client, create_poll):
        """Genau *eine* Weiterleitung, nicht erst der Umzug und dann die Weiche.

        Die `is_active`-Weiche steht deshalb seit B9 vor dem Umzug.
        """
        poll, tokens = create_poll()
        poll.is_active = False
        poll.save()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"


@pytest.mark.django_db
class TestTokenLeavesTheUrl:
    """B9: der Token zieht beim ersten Aufruf aus dem Query-String in ein Cookie um.

    Der Link in der Mail bleibt unverändert -- er *muss* es, es sind Mails unterwegs (Regel 4/5).
    Neu ist nur, dass die Adresse, auf der der Browser stehen bleibt, keinen Token mehr trägt.

    **Grenze des Testclients:** sein Cookie-Speicher ist nur nach Namen sortiert und ignoriert
    `path`. Dass zwei Umfragen sich nicht ins Gehege kommen, ist deshalb über das Attribut geprüft
    und nicht über zwei nacheinander abgerufene Seiten -- das würde hier gelingen, wo ein Browser
    es gar nicht erst versuchen würde.
    """

    def test_the_token_is_moved_into_a_cookie(self, client, create_poll):
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/"
        assert response.cookies[TOKEN_COOKIE_NAME].value == tokens[0]

    def test_the_page_after_the_move_shows_the_token(self, client, create_poll):
        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        response = client.get(f"/vote/{poll.identifier}/")
        assert response.context["token"] == tokens[0]
        assert response.context["error_message"] is None

    def test_the_move_happens_only_once(self, client, create_poll):
        """Kein Pendeln: die Zieladresse trägt keinen Token, also löst sie keinen Umzug aus."""
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        assert len(response.redirect_chain) == 1
        assert response.status_code == 200

    def test_the_cookie_is_scoped_to_this_poll(self, client, create_poll):
        """Ohne `path` würde eine zweite Einladung die erste überschreiben.

        Mit `?token=` in der URL gab es diese Kollision nicht -- die Bindung an den Pfad ist
        Verhaltenserhaltung und keine Zugabe.
        """
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.cookies[TOKEN_COOKIE_NAME]["path"] == f"/vote/{poll.identifier}/"

    def test_the_cookie_reaches_the_vote_endpoint(self, client, create_poll):
        """Der Cookie-Pfad darf nicht so eng sein, dass die Stimmabgabe ihn nicht mehr sieht.

        Ein Cookie geht an jeden Pfad, der mit seinem `path` beginnt. Geprüft wird deshalb gegen
        die echten Routen, nicht gegen ein zweites Mal hingeschriebene Zeichenketten.
        """
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        cookie_path = response.cookies[TOKEN_COOKIE_NAME]["path"]
        assert cookie_path.endswith("/"), "sonst greift die Präfixregel nicht"
        for name in ("vote", "success", "result"):
            assert reverse(f"vote:polls:{name}", args=(poll.identifier,)).startswith(cookie_path)

    def test_the_cookie_is_hidden_from_scripts_and_lax(self, client, create_poll):
        """`Lax`, nicht `Strict`: der Klick aus einem Webmailer ist seitenübergreifend."""
        poll, tokens = create_poll()
        cookie = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}).cookies[
            TOKEN_COOKIE_NAME
        ]
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"

    def test_the_cookie_follows_the_session_cookie_setting(self, client, create_poll, settings):
        """Ein eigener Schalter würde still von dem abweichen, den das Prod-Modul schon setzt."""
        poll, tokens = create_poll()
        assert not client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}).cookies[
            TOKEN_COOKIE_NAME
        ]["secure"]
        settings.SESSION_COOKIE_SECURE = True
        assert client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}).cookies[
            TOKEN_COOKIE_NAME
        ]["secure"]

    def test_an_empty_token_in_the_url_clears_the_cookie(self, client, create_poll):
        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        response = client.get(f"/vote/{poll.identifier}/", {"token": ""}, follow=True)
        assert response.context["token"] == ""

    def test_the_page_varies_on_cookie(self, client, create_poll):
        """Ein gemeinsamer Cache darf die Seite eines Wählers nicht an den nächsten ausliefern."""
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/")
        assert "Cookie" in response.headers["Vary"]

    def test_the_vote_takes_its_token_from_the_form_not_the_cookie(self, client, create_poll):
        """Das Cookie ist eine Bequemlichkeit für die Anzeige, kein Auth-Kanal für die Abgabe."""
        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[1], "choice": poll.choice_set.first().id},
        )
        assert Token.objects.filter(token_string=tokens[0]).exists(), "der falsche wurde verbraucht"
        assert not Token.objects.filter(token_string=tokens[1]).exists()

    def test_a_spent_token_still_explains_itself(self, client, create_poll):
        """Nach der Abgabe bleibt das Cookie stehen -- absichtlich.

        Es zeigt dann dieselbe Meldung wie bisher ein erneut aufgerufener Mail-Link. Löschen wäre
        die Alternative und würde die Erklärung durch ein leeres Feld ersetzen.
        """
        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[0], "choice": poll.choice_set.first().id},
        )
        response = client.get(f"/vote/{poll.identifier}/")
        assert (
            response.context["error_message"] == "This token is invalid. Maybe you voted already?"
        )

    def test_voting_already_required_a_cookie_before_all_this(self, create_poll):
        """Warum der Umzug in ein Cookie niemandem etwas wegnimmt: gemessen, nicht gehofft.

        Djangos CSRF-Prüfung verlangt schon heute ein Cookie. Wer keine annimmt, konnte auch
        vorher nicht abstimmen -- ein zweites Cookie kostet also keinen Wähler.
        """
        poll, tokens = create_poll()
        strict = Client(enforce_csrf_checks=True)
        page = strict.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        payload = {
            "token": tokens[0],
            "choice": poll.choice_set.first().id,
            "csrfmiddlewaretoken": str(page.context["csrf_token"]),
        }
        strict.cookies.clear()
        assert strict.post(f"/vote/{poll.identifier}/vote", payload).status_code == 403


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
class TestManageShowsTheSendState:
    """Versandstand auf der Manage-Seite. Warum ein Satz statt „n für diese Umfrage": Plan §11.7."""

    def test_it_says_something_is_queued_right_after_creating(self, client, create_poll):
        poll, _ = create_poll(send=False)
        content = client.get(f"/vote/{poll.identifier}/manage").content.decode()
        assert "Invitations are still queued" in content

    def test_it_says_nothing_is_waiting_once_the_queue_is_empty(self, client, create_poll):
        poll, _ = create_poll()
        assert OutgoingMail.objects.count() == 0
        content = client.get(f"/vote/{poll.identifier}/manage").content.decode()
        assert "No invitations are waiting" in content

    def test_it_is_a_bit_and_not_a_number(self, client, create_poll):
        """Eine Zahl wäre eine Aussage über *andere* Umfragen; die Seite braucht keinen Token."""
        poll, _ = create_poll(send=False, voters=tuple(f"w{i}@example.org" for i in range(7)))
        content = client.get(f"/vote/{poll.identifier}/manage").content.decode()
        assert "8" not in content.split("Invitations are still queued")[0][-200:]
        assert client.get(f"/vote/{poll.identifier}/manage").context["mails_pending"] is True

    def test_a_foreign_poll_in_the_queue_does_not_claim_to_be_this_one(self, client, create_poll):
        """Wartet etwas, kann es eine andere Umfrage sein -- die Seite behauptet nichts anderes."""
        poll, _ = create_poll()
        create_poll(title="Andere", send=False)
        content = client.get(f"/vote/{poll.identifier}/manage").content.decode()
        assert "Invitations are still queued for sending." in content
        assert poll.title not in content.split("Invitations are still queued")[1]


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

    def test_the_token_move_stores_nothing_on_the_server(self, client, create_poll):
        """Der Umzug aus der URL ins Cookie (B9, Plan 3.9) legt **keinen** Serverzustand an.

        Das ist die Zusage, die eine Session-basierte Lösung nicht hätte: die hätte für jeden
        Besucher eine Zeile in `django_session` geschrieben -- einen Schreibzugriff auf dieselbe
        SQLite-Datei, die vier uwsgi-Prozesse teilen (B13), und ein serverseitiges Gegenstueck zur
        Paarung Adresse-zu-Token, das F8 gerade *nicht* will.

        Dieser Test hält jemanden auf, der den Umzug später auf `request.session` umstellt.
        """
        from django.contrib.sessions.models import Session

        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        assert Session.objects.count() == 0

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
