"""Gemeinsame Helfer für die Testsuite.

Die Suite ist gegen das in Phase 0 protokollierte Ist-Verhalten geschrieben
(siehe notes/phase-0-baseline.md) und dient als Netz für die Umbauten in Phase 3.
"""

import re

import pytest

from vote.models import Poll

#: In der Wähler-Mail steht der Abstimmungslink mit angehängtem Token.
TOKEN_IN_URL = re.compile(r"\?token=([A-Za-z0-9]+)")

CREATOR_MAIL = "admin@example.org"


@pytest.fixture
def create_poll(client, mailoutbox, django_capture_on_commit_callbacks):
    """Legt über die echte create-View eine Umfrage an und liefert (poll, tokens).

    Absichtlich über HTTP und nicht über die ORM-Objekte: die Token-Vergabe passiert in der
    View, und genau die soll getestet werden.

    Der Versand hängt seit 3.4 an `transaction.on_commit` (B7). Ein `django_db`-Test läuft in
    einer Transaktion, die nie committet wird -- ohne dieses Capture käme also nie eine Mail an,
    und alles, was Tokens aus Mails liest, hätte nichts zu lesen.
    """

    def _create(
        *,
        title="Testabstimmung",
        poll_type="simple_choice",
        choices="Ja\nNein",
        voters=("erste@example.org", "zweite@example.org"),
        description="Wollen wir das?",
        creator_mail=CREATOR_MAIL,
    ):
        mailoutbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
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
        assert response.status_code == 200, "create sollte die Bestätigungsseite rendern"
        poll = Poll.objects.get(title=title)
        return poll, voter_tokens(mailoutbox, creator_mail=creator_mail)

    return _create


def voter_tokens(mailoutbox, creator_mail=CREATOR_MAIL):
    """Alle Tokens aus den Wähler-Mails, in Versandreihenfolge."""
    tokens = []
    for message in mailoutbox:
        if message.to == [creator_mail]:
            continue
        match = TOKEN_IN_URL.search(message.body)
        assert match, f"kein Token im Mailtext an {message.to}"
        tokens.append(match.group(1))
    return tokens


def creator_message(mailoutbox, creator_mail=CREATOR_MAIL):
    """Die Mail an den Umfrage-Ersteller."""
    matches = [m for m in mailoutbox if m.to == [creator_mail]]
    assert len(matches) == 1, f"genau eine Admin-Mail erwartet, {len(matches)} gefunden"
    return matches[0]
