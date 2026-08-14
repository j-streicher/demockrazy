"""The bugs confirmed in phase 0, written as the behaviour that is wanted.

**There is no `xfail` left here at the moment** -- every bug this file describes is fixed, and the
tests stand without a marker as regression tests. The numbers (B2, B3, ...) stay as a reference into
notes/plan.md §2.

The pattern for the next bug is still this one: `xfail(strict=True)`, the test describes what
*should* happen and fails today. As soon as someone fixes it, it turns into an unexpected pass --
which makes the suite red and is a reminder to remove the marker.

A lesson from 3.8: the *expectation* can fall together with the marker. The B4 test demanded a
rejecting status code while the measure was still open; a cap in the form produces a 200 with an
error message. What is checked now is the effect, not the status code.

Fixed: B3, B6, B11, B12 (plan 3.2) · B2 (plan 3.3) · the two unique constraints (plan 3.6) · B4
(plan 3.8) · B10 (plan 4.2) · B9 (plan 3.9). With that the register is worked through completely.
B15 only showed up in 3.3 and was fixed immediately, so it never had a marker -- its regression
tests sit in test_views.py with the other voting tests.
"""

import json

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from vote.models import Poll, Token

from .conftest import CREATOR_MAIL


@pytest.fixture
def lenient_client():
    """Returns a 500 on an exception instead of letting it through.

    What matters here is which *response* the user gets, not the traceback.
    """
    return Client(raise_request_exception=False)


def _create_payload(**overrides):
    payload = {
        "title": "Bugtest",
        "type": "simple_choice",
        "description": "?",
        "choices": "Ja\nNein",
        "creator_mail": CREATOR_MAIL,
        "voter_mails": "a@example.org\nb@example.org",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_b3_get_on_create_does_not_crash(lenient_client):
    """GET /vote/create should show the form or redirect, not die with a 500."""
    response = lenient_client.get("/vote/create")
    assert response.status_code != 500


@pytest.mark.django_db
def test_b3_invalid_poll_type_is_a_form_error(lenient_client):
    """An unknown type should come back as a form error, not as a 500."""
    response = lenient_client.post("/vote/create", _create_payload(type="quatsch"))
    assert response.status_code != 500
    assert not Poll.objects.filter(title="Bugtest").exists()


@pytest.mark.django_db
def test_b12_invalid_mail_address_is_a_form_error(lenient_client):
    """A broken address should produce an error message and create no poll."""
    response = lenient_client.post(
        "/vote/create", _create_payload(voter_mails="gueltig@example.org\nKAPUTT")
    )
    assert response.status_code != 500
    assert not Poll.objects.filter(title="Bugtest").exists()


@pytest.mark.django_db
def test_b6_duplicate_addresses_get_one_token_each(client):
    """The same address entered three times must not produce three votes."""
    client.post("/vote/create", _create_payload(voter_mails="dup@example.org\n" * 3))
    poll = Poll.objects.get(title="Bugtest")
    assert poll.num_tokens == 1
    assert poll.token_set.count() == 1


@pytest.mark.django_db
def test_b2_vote_without_token_field_shows_an_error(lenient_client, create_poll):
    """A missing token field should produce an error message, not an UnboundLocalError."""
    poll, _ = create_poll()
    response = lenient_client.post(
        f"/vote/{poll.identifier}/vote", {"choice": poll.choice_set.first().id}
    )
    assert response.status_code != 500
    assert response.context["error_message"] == "invalid token."
    assert poll.choice_set.first().votes == 0, "without a token no vote may be counted"
    assert poll.token_set.count() == 2, "and no token consumed"


@pytest.mark.django_db
def test_b11_manage_without_token_field_shows_an_error(lenient_client, create_poll):
    poll, _ = create_poll()
    response = lenient_client.post(f"/vote/{poll.identifier}/manage", {})
    assert response.status_code != 500
    assert response.context["error_message"] == "Wrong management token"
    poll.refresh_from_db()
    assert poll.is_active is True, "a poll must not be closed without the token"


@pytest.mark.django_db
def test_b4_poll_creation_is_not_wide_open(client, mailoutbox):
    """An anonymous request must not send arbitrarily many mails through the SMTP server.

    F5 is decided: a cap on the number of recipients, no per-IP rate limit (plan 3.8).

    **The expectation changed with that decision.** While the measure was still open, this test
    demanded a rejecting status code (400/401/403/429). But a cap in the form produces a 200 with an
    error message -- like any other invalid input, and for the same reason: the creator should get
    their list back and be able to trim it, not end up in a dead end (plan 3.2). So what is checked
    is not the code but the effect: no poll appears and no mail goes out.
    """
    response = client.post(
        "/vote/create",
        _create_payload(voter_mails="\n".join(f"opfer{i}@example.org" for i in range(500))),
    )
    assert response.status_code == 200
    assert not Poll.objects.filter(title="Bugtest").exists()
    assert mailoutbox == [], "not to the creator either"
    assert "At most 150 recipients" in response.content.decode()


@pytest.mark.django_db
def test_b10_special_characters_survive_into_the_chart(client):
    """The text in the chart has to be the text the creator typed.

    It used to be `name: '{{ choice.choice_text }}'` inside a JS string literal. Django escaped for
    HTML, but the content of a <script> element is not entity-decoded -- `Bier & Brezn` became a
    visible `Bier &amp; Brezn` in the chart. Measured, not assumed: that held for `&`, `'`, `"` and
    `<`.
    """
    poll = Poll.objects.create(title="P", question_text="?", num_tokens=0, is_active=False)
    texts = ["Bier & Brezn", "Annas 'Wahl'", "<b>fett</b>", 'Anfuehrung "so"']
    for text in texts:
        poll.choice_set.create(choice_text=text, votes=1)

    content = client.get(f"/vote/{poll.identifier}/results").content.decode()
    payload = content.split('id="chart-series"')[1].split("</script>")[0]
    series = json.loads(payload.split(">", 1)[1])

    assert [entry["name"] for entry in series][: len(texts)] == texts
    # And the counter-check for what json_script is actually for: no `</script>` breaks out.
    assert "</script>" not in payload.split(">", 1)[1]


@pytest.mark.django_db
def test_b9_the_browser_does_not_keep_the_token_in_the_url(client, create_poll):
    """The address the browser comes to rest on must not carry a token.

    `?token=…` was the only credential and therefore appeared in the nginx access log, in the
    browser history and -- because the referrer policy sends the full URL for same-origin requests
    -- in the `Referer` of every request the page triggers, so in every log line about a stylesheet
    too.

    The fix is **additive** (rules 4/5): the link in the mail stays character-identical, the token
    moves into a cookie on the first request. **What stays open and has to stay open:** the log line
    of that *one* request. It hangs off a clickable link and can only be solved at the proxy
    (`log_format` without `$args`) -- see notes/to-check.md.

    The mechanics of the move are in test_views.py::TestTokenLeavesTheUrl.
    """
    poll, tokens = create_poll()
    response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)

    final_url, status = response.redirect_chain[-1]
    assert status == 302
    assert tokens[0] not in final_url
    assert "token" not in final_url
    # And the page is still the right one: the token is in the form, only not in the URL.
    assert response.status_code == 200
    assert response.context["token"] == tokens[0]


@pytest.mark.django_db
def test_token_string_is_unique():
    """Since 3.6 the database enforces this instead of relying on a check beforehand."""
    from django.db import IntegrityError

    poll = Poll.objects.create(title="P", question_text="?")
    Token.objects.create(poll=poll, token_string="derselbe")
    with pytest.raises(IntegrityError):
        Token.objects.create(poll=poll, token_string="derselbe")


@pytest.mark.django_db
def test_poll_identifier_is_unique():
    from django.db import IntegrityError

    Poll.objects.create(title="A", question_text="?", identifier="dieselbe")
    with pytest.raises(IntegrityError):
        Poll.objects.create(title="B", question_text="?", identifier="dieselbe")


@pytest.mark.django_db
class TestR41TokenConsumptionGatesTheVote:
    """R4-1: a vote is only recorded when *this* request removed the token.

    The finding came out of a measurement with real threads (notes/review_probes.py): two concurrent
    POSTs with the same token produced two votes in 4 out of 100 rounds, both with a 302 to the
    success page. The cause was the order -- read token, record vote, delete token -- and that
    `delete()` does nothing, silently, on a row that has disappeared.

    A test with threads would do badly here: at a hit rate of ~4 % per round it would often be green
    even with broken code, and a test that does not fail reliably is error class K4. So what is
    checked is the *structure* that makes the case impossible -- against the statements the request
    really issued.
    """

    def test_the_token_is_deleted_before_the_vote_is_counted(self, client, create_poll):
        poll, tokens = create_poll()
        with CaptureQueriesContext(connection) as queries:
            response = client.post(
                f"/vote/{poll.identifier}/vote",
                {"token": tokens[0], "choice": poll.choice_set.first().pk},
            )
        assert response.status_code == 302

        statements = [entry["sql"] for entry in queries.captured_queries]
        deletes = [i for i, sql in enumerate(statements) if 'DELETE FROM "vote_token"' in sql]
        updates = [i for i, sql in enumerate(statements) if 'UPDATE "vote_choice"' in sql]
        assert len(deletes) == 1, statements
        assert updates, statements
        assert deletes[0] < updates[0], (
            "The vote was recorded before the token was consumed -- exactly the order that "
            "produces two votes from one token."
        )

    def test_the_token_is_never_looked_up_by_its_string(self, client, create_poll):
        """The deletion *is* the check -- there is no query for the token before it.

        A `Token.objects.get(token_string=...)` moved in front would be the hole again: between it
        and the write lies the window in which a second request reads the same token. The `COUNT(*)`
        query that closes the poll only counts rows and is not what is meant here.
        """
        poll, tokens = create_poll()
        with CaptureQueriesContext(connection) as queries:
            client.post(
                f"/vote/{poll.identifier}/vote",
                {"token": tokens[0], "choice": poll.choice_set.first().pk},
            )
        lookups = [
            entry["sql"]
            for entry in queries.captured_queries
            if entry["sql"].lstrip().startswith("SELECT") and "token_string" in entry["sql"]
        ]
        assert lookups == [], lookups

    def test_a_token_that_is_gone_books_nothing(self, client, create_poll):
        """The case the deletion-as-condition catches -- staged here without concurrency.

        The token disappears between rendering the page and submitting the form; the response has to
        be the same as for an unknown token, and no vote may stand.
        """
        poll, tokens = create_poll()
        choice = poll.choice_set.first()
        Token.objects.filter(token_string=tokens[0]).delete()

        response = client.post(
            f"/vote/{poll.identifier}/vote", {"token": tokens[0], "choice": choice.pk}
        )
        choice.refresh_from_db()
        assert response.status_code == 200
        assert response.context["error_message"] == "invalid token."
        assert choice.votes == 0

    def test_multiple_choice_counts_at_most_once_per_token(self, client, create_poll):
        """The same promise for the path that touches several counters."""
        poll, tokens = create_poll(poll_type="multiple_choice", choices="Bier\nBrezn")
        payload = {"token": tokens[0]}
        for choice in poll.choice_set.all():
            payload[f"choice{choice.id}"] = "yes"

        assert client.post(f"/vote/{poll.identifier}/vote", payload).status_code == 302
        second = client.post(f"/vote/{poll.identifier}/vote", payload)

        assert second.status_code == 200
        assert second.context["error_message"] == "invalid token."
        assert [choice.votes for choice in poll.choice_set.all()] == [1, 1]
