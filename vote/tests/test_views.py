"""Tests for vote/views.py against the behaviour recorded in phase 0."""

import re
from typing import ClassVar

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import Resolver404, resolve, reverse

from vote.models import Choice, OutgoingMail, Poll, Token
from vote.services import mail
from vote.views import TOKEN_COOKIE_NAME

from .conftest import CREATOR_MAIL, creator_message, voter_tokens

#: Input that is broken in exactly one place -- the rest has to survive the error page.
INVALID_PAYLOAD = {
    "title": "Wiedervorlage",
    "type": "simple_choice",
    "description": "Wollen wir das?",
    "choices": "Ja\nNein",
    "creator_mail": CREATOR_MAIL,
    "voter_mails": "gueltig@example.org\nKAPUTT",
}


class TestUrls:
    """Mails with ?token= links to existing polls are out there.

    These paths must not change while modernising (plan rule 4).
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
        """The counter-check for the converter of our own from vote/urls.py.

        `mk_identifier()` only draws from `ascii_letters + digits`. Django's `slug`
        would also have accepted `-` and `_`, so more than the old `re_path`
        expression -- and that must not reach the view.
        """
        with pytest.raises(Resolver404):
            resolve(f"/vote/{identifier}/")


@pytest.mark.django_db
class TestPageTitles:
    """R13-1: the `{% block title %}` in base.html existed and stayed empty in every template.

    All six pages were called "Demockrazy". WCAG 2.4.2 asks for a title that describes topic or
    purpose, and practically: whoever has two polls open cannot tell the tabs apart.
    """

    #: The separator is an en dash; written as an escape because ruff otherwise reports it in the
    #: source as an ambiguous character (RUF001) and a `noqa` does not belong here.
    SUFFIX = " \u2013 Demockrazy"

    def _title(self, client, path):
        found = re.search(r"<title>(.*?)</title>", client.get(path).content.decode())
        assert found, f"no title in {path}"
        return found.group(1)

    def test_each_page_says_what_it_is(self, client, create_poll):
        poll, _ = create_poll(title="Kantinenwahl")
        expected = {
            "/vote/": "Create a new poll",
            f"/vote/{poll.identifier}/": "Kantinenwahl",
            f"/vote/{poll.identifier}/manage": "Manage Kantinenwahl",
            f"/vote/{poll.identifier}/success": "Thanks for voting on Kantinenwahl",
        }
        for path, text in expected.items():
            assert self._title(client, path) == text + self.SUFFIX, path

    def test_the_results_page_names_the_poll(self, client, create_poll):
        poll, tokens = create_poll(title="Kantinenwahl")
        for token in tokens:
            client.post(
                f"/vote/{poll.identifier}/vote",
                {"token": token, "choice": poll.choice_set.first().id},
            )
        title = self._title(client, f"/vote/{poll.identifier}/results")
        assert title == "Results for Kantinenwahl" + self.SUFFIX

    def test_the_confirmation_page_has_its_own_title(self, client):
        payload = dict(INVALID_PAYLOAD, voter_mails="a@example.org")
        content = client.post("/vote/create", payload).content.decode()
        assert f"<title>Poll created{self.SUFFIX}</title>" in content


class TestIndex:
    def test_renders_form(self, client):
        response = client.get("/vote/")
        assert response.status_code == 200
        assert b'name="voter_mails"' in response.content

    def test_clean_form_carries_no_aria_error_markup(self, client):
        """The counter-check to the test below: without errors the form claims none (plan 4.5)."""
        content = client.get("/vote/").content
        assert b"aria-invalid" not in content
        assert b"aria-describedby" not in content

    @pytest.mark.django_db
    def test_field_error_is_announced_at_the_field(self, client):
        """The error list sits next to the field visually -- a screen reader needs the link.

        `voter_mails` is the broken field in INVALID_PAYLOAD, `title` the intact one beside it.
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
    """`create()` enqueues the mails and sends nothing itself (plan §11.7).

    This is the new shape of the promise from B7 ("no mail before the tokens are durable"): it no
    longer rests on an `on_commit` callback but on the fact that **another process** does the
    sending and only sees committed rows.
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
        assert mailoutbox == [], "the request itself must not send a mail"

    def test_one_queue_row_per_recipient_plus_the_creator(self, client):
        client.post("/vote/create", self.PAYLOAD)
        assert OutgoingMail.objects.count() == 3

    def test_the_creator_comes_first(self, client):
        client.post("/vote/create", self.PAYLOAD)
        recipients = list(OutgoingMail.objects.order_by("pk").values_list("recipient", flat=True))
        assert recipients == [CREATOR_MAIL, "a@example.org", "b@example.org"]

    def test_a_queue_row_does_not_name_its_poll(self, client):
        """F8: a row should not say on its own which poll it belongs to.

        Checked against the fields and not the content: a foreign key or an identifier column would
        be exactly what must not appear here. The *text* names the title of course -- it is the
        invitation.
        """
        client.post("/vote/create", self.PAYLOAD)
        columns = {field.name for field in OutgoingMail._meta.get_fields()}
        assert columns == {"id", "recipient", "subject", "body", "attempts"}
        assert not any(field.is_relation for field in OutgoingMail._meta.get_fields())

    def test_an_invalid_form_queues_nothing(self, client):
        client.post("/vote/create", {**self.PAYLOAD, "voter_mails": "KAPUTT"})
        assert OutgoingMail.objects.count() == 0

    def test_the_queue_survives_into_a_real_transaction(self, client, mailoutbox):
        """The counter-check with a real commit: no test mechanism helps out here.

        This used to be the counter-check for `on_commit` -- that sending works without executing
        the callbacks by hand. The promise is a different one now: after the commit the rows are
        there, and only a separate run sends them.
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
    """The error path of `create()`, since it goes through `PollCreateForm` (plan 3.2)."""

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
        """Not to the creator either -- otherwise a loop of typos would be a mail sender."""
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            client.post("/vote/create", INVALID_PAYLOAD)
        assert callbacks == [], "an invalid form must not schedule any sending"
        assert mailoutbox == []

    def test_the_entered_values_survive_an_error(self, client):
        """Whoever pastes 200 addresses should not retype them after one typo."""
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
    """`follow=True`, because since B9 a token in the URL first moves and then redirects.

    What happens on the way is checked by `TestTokenLeavesTheUrl`; only the page at the end matters
    here.
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
        """No token, no move, no error message -- only an empty field to type into."""
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
        """Exactly *one* redirect, not the move first and then the branch.

        Which is why the `is_active` branch has sat in front of the move since B9.
        """
        poll, tokens = create_poll()
        poll.is_active = False
        poll.save()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.status_code == 302
        assert response.headers["Location"] == f"/vote/{poll.identifier}/results"


@pytest.mark.django_db
class TestTokenLeavesTheUrl:
    """B9: on the first request the token moves out of the query string into a cookie.

    The link in the mail stays unchanged -- it *has* to, mails are out there (rules 4/5). All that
    is new is that the address the browser comes to rest on carries no token any more.

    **A limit of the test client:** its cookie jar is keyed by name only and ignores `path`. That
    two polls do not get in each other's way is therefore checked through the attribute and not
    through two pages fetched one after the other -- that would succeed here where a browser would
    not even try.
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
        """No ping-pong: the target address carries no token, so it triggers no move."""
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)
        assert len(response.redirect_chain) == 1
        assert response.status_code == 200

    def test_the_cookie_is_scoped_to_this_poll(self, client, create_poll):
        """Without `path` a second invitation would overwrite the first.

        With `?token=` in the URL that collision did not exist -- binding to the path preserves
        behaviour, it does not add any.
        """
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.cookies[TOKEN_COOKIE_NAME]["path"] == f"/vote/{poll.identifier}/"

    def test_the_cookie_reaches_the_vote_endpoint(self, client, create_poll):
        """The cookie path must not be so narrow that the vote itself no longer sees it.

        A cookie goes to every path that starts with its `path`. So this is checked against the real
        routes, not against strings written out a second time.
        """
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        cookie_path = response.cookies[TOKEN_COOKIE_NAME]["path"]
        assert cookie_path.endswith("/"), "otherwise the prefix rule does not apply"
        for name in ("vote", "success", "result"):
            assert reverse(f"vote:polls:{name}", args=(poll.identifier,)).startswith(cookie_path)

    def test_the_cookie_is_hidden_from_scripts_and_lax(self, client, create_poll):
        """`Lax`, not `Strict`: the click from a webmail client is cross-site."""
        poll, tokens = create_poll()
        cookie = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}).cookies[
            TOKEN_COOKIE_NAME
        ]
        assert cookie["httponly"]
        assert cookie["samesite"] == "Lax"

    def test_the_cookie_follows_the_session_cookie_setting(self, client, create_poll, settings):
        """A switch of its own would silently drift from the one production already sets."""
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

    @pytest.mark.parametrize(
        "value,label",
        [
            ("a\r\nSet-Cookie: admin=1", "control character"),
            ("\u2713", "beyond Latin-1"),
            ("x" * 300, "too long"),
            ("kein token!", "special characters"),
        ],
    )
    def test_a_token_that_cannot_be_one_is_treated_as_none(self, client, create_poll, value, label):
        """R3-1: the value went into `set_cookie()` unchecked -- two of these cases were a 500.

        A control character makes `http.cookies` raise a `CookieError`, a character beyond Latin-1
        produces a Set-Cookie header that WSGI must not carry. One answer for both: what cannot be a
        token is not one -- so the same path as `?token=` without a value.
        """
        poll, _ = create_poll()
        strict = Client(raise_request_exception=True)
        response = strict.get(f"/vote/{poll.identifier}/", {"token": value})

        assert response.status_code == 302, label
        cookie = response.cookies.get(TOKEN_COOKIE_NAME)
        assert cookie is not None and cookie.value == "", (
            f"{label}: instead of a cookie with a crooked value, an existing one must be deleted"
        )
        for part in str(cookie).splitlines():
            part.encode("latin-1")  # a WSGI requirement; raises UnicodeEncodeError otherwise

    def test_a_real_token_still_moves(self, client, create_poll):
        """The counter-check to the check: the real value arrives in the cookie unchanged."""
        poll, tokens = create_poll()
        response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert response.cookies[TOKEN_COOKIE_NAME].value == tokens[0]

    def test_the_page_varies_on_cookie(self, client, create_poll):
        """A shared cache must not hand one voter's page to the next.

        R10-1: this test passed **without** `@vary_on_cookie` as well. It looked the header up on
        the form page, and there the CSRF middleware already sets it, because the template contains
        a `{% csrf_token %}` -- so it could not fail. It is therefore checked against responses that
        contain **no form**: the two redirects of this view. There, `Vary: Cookie` is only present
        if the decorator sets it.
        """
        poll, tokens = create_poll()

        moved = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        assert moved.status_code == 302
        assert "Cookie" in moved.headers["Vary"], "the move redirect does not carry the header"

        poll.is_active = False
        poll.save()
        closed = client.get(f"/vote/{poll.identifier}/")
        assert closed.status_code == 302
        assert "Cookie" in closed.headers["Vary"]

        # And still on the page itself -- with belt and braces there.
        poll.is_active = True
        poll.save()
        assert "Cookie" in client.get(f"/vote/{poll.identifier}/").headers["Vary"]

    def test_the_page_with_the_token_is_not_cacheable(self, client, create_poll):
        """R6-2: `Vary: Cookie` only says *what* a cache distinguishes by -- not that it should not
        store at all.

        The page shows the token in the form; it must lie neither in a shared cache nor on the
        browser's disk. The same holds for the manage page, which accepts the management token.
        """
        poll, _ = create_poll()
        for path in (f"/vote/{poll.identifier}/", f"/vote/{poll.identifier}/manage"):
            cache_control = client.get(path).headers["Cache-Control"]
            assert "no-store" in cache_control, path

    def test_the_vote_takes_its_token_from_the_form_not_the_cookie(self, client, create_poll):
        """The cookie is a convenience for the display, not an auth channel for the vote."""
        poll, tokens = create_poll()
        client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]})
        client.post(
            f"/vote/{poll.identifier}/vote",
            {"token": tokens[1], "choice": poll.choice_set.first().id},
        )
        assert Token.objects.filter(token_string=tokens[0]).exists(), "the wrong one was consumed"
        assert not Token.objects.filter(token_string=tokens[1]).exists()

    def test_a_spent_token_still_explains_itself(self, client, create_poll):
        """After voting the cookie stays -- deliberately.

        It then shows the same message a mail link opened a second time used to show. Deleting it
        would be the alternative and would replace the explanation with an empty field.
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
        """Why moving into a cookie takes nothing away from anyone: measured, not hoped.

        Django's CSRF check already demands a cookie today. Whoever accepts none could not vote
        before either -- so a second cookie costs no voter.
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
        """B15: a non-numeric value ran into a ValueError from the pk lookup, so a 500."""
        poll, tokens = create_poll()
        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": value}
        )
        assert response.status_code == 200
        assert response.context["error_message"] == "You didn't select a choice."
        assert Token.objects.filter(token_string=tokens[0]).exists()
        assert poll.choice_set.first().votes == 0

    def test_get_does_not_crash(self, client, create_poll):
        """Without POST data there is no token -- that is an error message, not a 500."""
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
        """The important part: the partial vote must not count and the token has to survive."""
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
    """The send state on the manage page. Why a sentence and not "n for this poll": plan §11.7."""

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
        """A number would be a statement about *other* polls; the page needs no token."""
        poll, _ = create_poll(send=False, voters=tuple(f"w{i}@example.org" for i in range(7)))
        content = client.get(f"/vote/{poll.identifier}/manage").content.decode()
        assert "8" not in content.split("Invitations are still queued")[0][-200:]
        assert client.get(f"/vote/{poll.identifier}/manage").context["mails_pending"] is True

    def test_a_foreign_poll_in_the_queue_does_not_claim_to_be_this_one(self, client, create_poll):
        """If something is queued it may be another poll -- the page claims nothing else."""
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

    def test_a_multiple_choice_vote_is_one_update(self, client, create_poll):
        """R11-1: previously one `UPDATE` per ticked choice, all of them under the write lock.

        On SQLite the `atomic()` block of the vote holds the write lock for all four uwsgi
        processes, so the number of statements inside it should not grow with the number of choices.
        """
        poll, tokens = create_poll(poll_type="multiple_choice", choices="\n".join("abcdefghij"))
        payload = {"token": tokens[0]}
        for choice in poll.choice_set.all():
            payload[f"choice{choice.id}"] = "yes"

        with CaptureQueriesContext(connection) as queries:
            response = client.post(f"/vote/{poll.identifier}/vote", payload)

        assert response.status_code == 302
        updates = [
            entry["sql"]
            for entry in queries.captured_queries
            if 'UPDATE "vote_choice"' in entry["sql"]
        ]
        assert len(updates) == 1, updates
        assert [choice.votes for choice in poll.choice_set.all()] == [1] * 10

    def test_abstentions_are_a_chart_segment_only_for_simple_choice(self, client, create_poll):
        """R10-3: the chart data for `multiple_choice` was covered by no test.

        With `simple_choice` the sum of the votes is the number of voters, so outstanding tokens are
        abstentions and a segment of their own. With `multiple_choice` nobody chose "nothing" -- an
        abstention segment there would be a claim the numbers do not support.
        """
        poll, tokens = create_poll(choices="Bier\nBrezn")
        choice = poll.choice_set.first()
        client.post(f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.id})
        poll.is_active = False
        poll.save()
        simple = client.get(f"/vote/{poll.identifier}/results").context["chart_series"]
        assert simple == [
            {"name": "Bier", "y": 1},
            {"name": "Brezn", "y": 0},
            {"name": "Abstentions", "y": 1},
        ]

        multiple_poll, multiple_tokens = create_poll(
            title="Mehrfach", poll_type="multiple_choice", choices="Bier\nBrezn"
        )
        payload = {"token": multiple_tokens[0]}
        for one in multiple_poll.choice_set.all():
            payload[f"choice{one.id}"] = "yes"
        client.post(f"/vote/{multiple_poll.identifier}/vote", payload)
        multiple_poll.is_active = False
        multiple_poll.save()
        multiple = client.get(f"/vote/{multiple_poll.identifier}/results").context["chart_series"]
        assert multiple == [{"name": "Bier", "y": 1}, {"name": "Brezn", "y": 1}]
        assert "Abstentions" not in [entry["name"] for entry in multiple]

    def test_success_page(self, client, create_poll):
        poll, _ = create_poll()
        response = client.get(f"/vote/{poll.identifier}/success")
        assert response.status_code == 200
        assert poll.title.encode() in response.content


@pytest.mark.django_db
class TestAnonymity:
    """The core promise: after voting there is no connection from voter to vote."""

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
        """The move from the URL into a cookie (B9, plan 3.9) creates **no** server state.

        That is the promise a session-based solution would not have: it would write a row in
        `django_session` for every visitor -- a write to the same SQLite file four uwsgi processes
        share (B13), and a server-side counterpart to the address-to-token pairing that F8
        explicitly does *not* want.

        This test stops anyone who later moves the whole thing onto `request.session`.
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
    """Guards the test helpers themselves, so an empty mailbox does not pass as success."""

    def test_voter_tokens_skips_the_creator_mail(self, create_poll, mailoutbox):
        create_poll(voters=("a@example.org", "b@example.org"))
        assert len(voter_tokens(mailoutbox)) == 2


@pytest.mark.django_db
class TestResultsTotals:
    def test_total_voters_is_the_computed_number_not_the_raw_field(self, client):
        """R14-1: `poll.num_tokens` is NULL for old polls and stood on the page as "None".

        `get_amount_used_unused()` handles that case explicitly ("old polls without a recipient
        list"); the template went around that care. Production has polls from before 2016.
        """
        poll = Poll.objects.create(title="Alt", question_text="?", num_tokens=None, is_active=False)
        poll.choice_set.create(choice_text="Ja", votes=3)

        content = client.get(f"/vote/{poll.identifier}/results").content.decode()

        assert "None" not in content
        row = content.split("Total Voters")[1]
        assert "<td>3</td>" in row

    def test_total_voters_still_matches_num_tokens_for_a_normal_poll(self, client, create_poll):
        """The counter-check: where `num_tokens` is set, the number does not change."""
        poll, tokens = create_poll(voters=("a@example.org", "b@example.org"))
        for token in tokens:
            client.post(
                f"/vote/{poll.identifier}/vote",
                {"token": token, "choice": poll.choice_set.first().id},
            )
        content = client.get(f"/vote/{poll.identifier}/results").content.decode()
        assert "<td>2</td>" in content.split("Total Voters")[1]
