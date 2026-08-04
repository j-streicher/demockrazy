"""Tests für den Management-Command `send_pending_mails`.

Der Command ist bewusst dünn -- die Arbeit steht in `vote.services.mail.send_pending()` und ist in
test_mail_service.py geprüft. Hier geht es um die Betriebsdinge: die **Sperre**, die Optionen und
den Ort der Sperrdatei.
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
    """Reine Funktion, damit der Test kein `DATABASES` überschreiben muss.

    Ein Override dort erzeugt bei jedem Test eine `UserWarning` -- dieselbe Überlegung wie bei
    `demockrazy/checks.py` (Plan 5.4).
    """

    def test_it_sits_next_to_the_database(self):
        """`BASE_DIR` ist in Produktion der read-only Nix-Store -- deshalb folgt die Sperrdatei
        der Datenbank und nicht dem Projektverzeichnis."""
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
        """Ein Lauf dauert Minuten, der Timer feuert im Minutentakt -- zwei gleichzeitige Läufe
        würden dieselben Zeilen greifen und doppelt verschicken.

        `flock` bindet an den geöffneten Deskriptor, nicht an den Prozess: ein zweiter `open()`
        derselben Datei kollidiert deshalb auch innerhalb dieses Tests.
        """
        enqueue(2)
        with lock_path().open("w") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            out = StringIO()
            call_command("send_pending_mails", "--pause", "0", stdout=out)
            assert "läuft schon" in out.getvalue()
        assert mailoutbox == [], "nichts verschickt"
        assert OutgoingMail.objects.count() == 2, "und nichts angefasst"

    def test_the_lock_is_released_afterwards(self, mailoutbox):
        """Sonst wäre der erste Lauf der letzte."""
        enqueue(1)
        call_command("send_pending_mails", "--pause", "0", stdout=StringIO())
        enqueue(1)
        call_command("send_pending_mails", "--pause", "0", stdout=StringIO())
        assert len(mailoutbox) == 2
