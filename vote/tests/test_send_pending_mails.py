"""Tests for the management command `send_pending_mails`.

The command is deliberately thin -- the work lives in `vote.services.mail.send_pending()` and is
checked in test_mail_service.py. This is about the operational parts: the **lock**, the options, and
where the lock file goes.
"""

import fcntl
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command

from vote.management.commands.send_pending_mails import lock_path
from vote.models import OutgoingMail
from vote.services import mail


def enqueue(count):
    mail.enqueue([(f"Betreff {i}", f"Text {i}", f"a{i}@example.org") for i in range(count)])


class TestLockPath:
    """A pure function, so the test does not have to override `DATABASES`.

    An override there produces a `UserWarning` in every test -- the same consideration as in
    `demockrazy/checks.py` (plan 5.4).
    """

    def test_it_sits_next_to_the_database(self):
        """In production `BASE_DIR` is the read-only Nix store -- which is why the lock file follows
        the database and not the project directory."""
        assert lock_path("/var/lib/demockrazy/db.sqlite3") == Path(
            "/var/lib/demockrazy/db.mailsend.lock"
        )

    @pytest.mark.parametrize("name", [":memory:", "file:memorydb?mode=memory&cache=shared"])
    def test_an_in_memory_database_has_no_neighbour(self, name):
        assert lock_path(name).name == "demockrazy-mailsend.lock"
        assert lock_path(name).is_absolute()


@pytest.mark.django_db
class TestCommand:
    def test_it_empties_the_queue(self, mailoutbox):
        enqueue(2)
        out = StringIO()
        call_command("send_pending_mails", "--pause", "0", stdout=out)
        assert len(mailoutbox) == 2
        assert OutgoingMail.objects.count() == 0
        assert "2 verschickt" in out.getvalue()

    def test_the_batch_size_option_wins_over_the_setting(self, settings, mailoutbox):
        settings.VOTE_MAIL_BATCH_SIZE = 30
        enqueue(4)
        out = StringIO()
        call_command("send_pending_mails", "--batch-size", "2", "--pause", "0", stdout=out)
        assert "2 Batches" in out.getvalue()

    def test_a_second_run_does_nothing_while_the_first_holds_the_lock(self, mailoutbox):
        """A run takes minutes, the timer fires every minute -- two concurrent runs would grab the
        same rows and send them twice.

        `flock` binds to the open descriptor, not to the process: a second `open()` of the same file
        therefore collides inside this test as well.
        """
        enqueue(2)
        with lock_path().open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out = StringIO()
            call_command("send_pending_mails", "--pause", "0", stdout=out)
            assert "läuft schon" in out.getvalue()
        assert mailoutbox == [], "nothing sent"
        assert OutgoingMail.objects.count() == 2, "and nothing touched"

    def test_the_lock_is_released_afterwards(self, mailoutbox):
        """Otherwise the first run would be the last one."""
        enqueue(1)
        call_command("send_pending_mails", "--pause", "0", stdout=StringIO())
        enqueue(1)
        call_command("send_pending_mails", "--pause", "0", stdout=StringIO())
        assert len(mailoutbox) == 2
