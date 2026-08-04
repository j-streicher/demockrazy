"""Gemeinsame Helfer für die Testsuite.

Die Suite ist gegen das in Phase 0 protokollierte Ist-Verhalten geschrieben
(siehe notes/phase-0-baseline.md) und dient als Netz für die Umbauten in Phase 3.
"""

import re

import pytest

from vote.models import Poll
from vote.services import mail

#: In der Wähler-Mail steht der Abstimmungslink mit angehängtem Token.
TOKEN_IN_URL = re.compile(r"\?token=([A-Za-z0-9]+)")

CREATOR_MAIL = "admin@example.org"


@pytest.fixture
def create_poll(client, mailoutbox):
    """Legt über die echte create-View eine Umfrage an, leert die Warteschlange, liefert
    (poll, tokens).

    Absichtlich über HTTP und nicht über die ORM-Objekte: die Token-Vergabe passiert in der
    View, und genau die soll getestet werden.

    **Der Versand ist seit Plan §11.7 nicht mehr Teil des Requests.** `create()` reiht die Mails
    nur ein; verschickt werden sie von einem Management-Command, den in Produktion ein
    systemd-Timer aufruft. Diese Fixture spielt beide Schritte, weil fast jeder Test die Tokens
    aus den *Mails* liest -- mit `pause=0`, damit die Suite nicht in echten Pausen wartet.
    Dass `create()` von sich aus nichts verschickt, prüft `test_views.py::TestCreateQueuesMails`.

    *(Hier stand vorher ein `django_capture_on_commit_callbacks`: der Versand hing an
    `transaction.on_commit`, und ein `django_db`-Test committet nie. Beides ist entfallen -- das
    Einreihen läuft jetzt in derselben Transaktion wie die Tokens, ohne Callback.)*
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
        assert response.status_code == 200, "create sollte die Bestätigungsseite rendern"
        if send:
            mail.send_pending(pause=0)
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
