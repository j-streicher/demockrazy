"""R2-1: what a staff account **cannot** do through `/admin/`.

The finding was not theoretical: `/admin/` has been routed since 2016, all three models were
registered without restriction, and the user confirmed that a staff account exists in production.
One password therefore opened the only path in the system that could change vote counts directly and
read every voter token.

The tests drive the real admin interface, not the `ModelAdmin` attributes: what should be checked is
the effect. `admin_client` (pytest-django) creates a superuser and logs it in -- so the strongest
case, not the weakest.
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
        # The number is still displayed -- just not as an input field.
        assert '<div class="readonly">7</div>' in content

    def test_a_posted_vote_count_is_ignored(self, admin_client, poll):
        """The actual proof: even a form that submits the field changes nothing."""
        choice = poll.choice_set.get()
        response = admin_client.post(
            f"/admin/vote/choice/{choice.pk}/change/",
            {"poll": poll.pk, "choice_text": "Pizza", "votes": "9999"},
        )
        choice.refresh_from_db()
        assert response.status_code in (200, 302)
        assert choice.votes == 7, "vote count changed through the admin form"

    def test_adding_a_choice_starts_at_zero(self, admin_client, poll):
        admin_client.post(
            "/admin/vote/choice/add/",
            {"poll": poll.pk, "choice_text": "Pasta", "votes": "500"},
        )
        created = Choice.objects.get(choice_text="Pasta")
        assert created.votes == 0


@pytest.mark.django_db
class TestTokensCannotBeRead:
    def test_the_voter_token_appears_neither_in_the_list_nor_in_the_form(self, admin_client, poll):
        token = poll.token_set.get()
        listing = admin_client.get("/admin/vote/token/").content.decode()
        form = admin_client.get(f"/admin/vote/token/{token.pk}/change/").content.decode()
        for page in (listing, form):
            assert token.token_string not in page
            assert 'name="token_string"' not in page

    def test_the_creator_token_is_not_shown_either(self, admin_client, poll):
        """It closes the poll early -- a secret that does not belong on a page."""
        listing = admin_client.get("/admin/vote/poll/").content.decode()
        form = admin_client.get(f"/admin/vote/poll/{poll.pk}/change/").content.decode()
        for page in (listing, form):
            assert poll.creator_token not in page
            assert 'name="creator_token"' not in page

    def test_the_identifier_cannot_be_changed(self, admin_client, poll):
        """Mails with links to this identifier are out there (working rule 5).

        The status code is part of the check: without it this test passes with the old registration
        too, because the POST fails there on a *different* missing required field, which leaves the
        identifier standing as well. A test that is green for the wrong reason is error class K4 --
        measured by restoring the old `admin.py`.
        """
        previous = poll.identifier
        form = admin_client.get(f"/admin/vote/poll/{poll.pk}/change/").content.decode()
        assert 'name="identifier"' not in form

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
        assert response.status_code == 302, "the POST has to go through, or the test checks nothing"
        assert poll.identifier == previous


@pytest.mark.django_db
class TestWhatStaysPossible:
    """The counter-check: the interface is cut back, not switched off."""

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
        assert poll.is_active is False, "the checkbox is absent from the POST, so the poll closes"

    def test_a_poll_can_still_be_deleted(self, admin_client, poll):
        admin_client.post(f"/admin/vote/poll/{poll.pk}/delete/", {"post": "yes"})
        assert not Poll.objects.filter(pk=poll.pk).exists()
        assert Token.objects.count() == 0, "the tokens hang off it via CASCADE"
