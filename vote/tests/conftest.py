"""Shared helpers for the test suite.

The suite is written against the behaviour recorded in phase 0 (see notes/phase-0-baseline.md) and
serves as the net for the rebuilds in phase 3.
"""

import re

import pytest

from vote.models import Poll
from vote.services import mail

#: The voter mail contains the voting link with the token appended.
TOKEN_IN_URL = re.compile(r"\?token=([A-Za-z0-9]+)")

CREATOR_MAIL = "admin@example.org"


@pytest.fixture
def create_poll(client, mailoutbox):
    """Creates a poll through the real create view, empties the queue, returns (poll, tokens).

    Deliberately over HTTP rather than through the ORM objects: handing out the tokens happens in
    the view, and that is exactly what should be tested.

    **Since plan §11.7 sending is no longer part of the request.** `create()` only enqueues the
    mails; they are sent by a management command that a systemd timer invokes in production. This
    fixture plays both steps, because almost every test reads the tokens from the *mails* -- with
    `pause=0`, so the suite does not wait through real pauses. That `create()` sends nothing by
    itself is checked by `test_views.py::TestCreateQueuesMails`.

    *(There used to be a `django_capture_on_commit_callbacks` here: sending hung off
    `transaction.on_commit`, and a `django_db` test never commits. Both are gone -- enqueueing now
    runs in the same transaction as the tokens, without a callback.)*
    """

    def _create(
        *,
        title="Testabstimmung",
        poll_type="simple_choice",
        choices="Ja\nNein",
        voters=("erste@example.org", "zweite@example.org"),
        description="Wollen wir das?",
        creator_mail=CREATOR_MAIL,
        send=True,
    ):
        mailoutbox.clear()
        response = client.post(
            "/vote/create",
            {
                "title": title,
                "type": poll_type,
                "description": description,
                "choices": choices,
                "creator_mail": creator_mail,
                "voter_mails": "\n".join(voters),
            },
        )
        assert response.status_code == 200, "create should render the confirmation page"
        if send:
            mail.send_pending(pause=0)
        poll = Poll.objects.get(title=title)
        return poll, voter_tokens(mailoutbox, creator_mail=creator_mail)

    return _create


def voter_tokens(mailoutbox, creator_mail=CREATOR_MAIL):
    """Every token from the voter mails, in sending order."""
    tokens = []
    for message in mailoutbox:
        if message.to == [creator_mail]:
            continue
        match = TOKEN_IN_URL.search(message.body)
        assert match, f"no token in the mail body to {message.to}"
        tokens.append(match.group(1))
    return tokens


def creator_message(mailoutbox, creator_mail=CREATOR_MAIL):
    """The mail to the poll's creator."""
    matches = [m for m in mailoutbox if m.to == [creator_mail]]
    assert len(matches) == 1, f"expected exactly one admin mail, found {len(matches)}"
    return matches[0]
