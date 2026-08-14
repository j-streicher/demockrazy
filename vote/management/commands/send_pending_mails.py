"""Sends the mail queue at a pace. Meant for a systemd timer.

The command is deliberately thin: the work lives in `vote.services.mail.send_pending()`, and only
the operational parts are here -- options, the **lock**, and a summary on stdout.

Why a lock of its own instead of relying on systemd: a run takes minutes (30 mails, then 2 s, then
the next ones), while the timer fires every minute. Two concurrent runs would grab the same rows and
send them twice. `flock` makes that impossible however the command is started -- including a run by
hand while the timer is working.
"""

import fcntl
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from vote.services import mail


def lock_path(database_name=None):
    """The lock file sits next to the database, not under `BASE_DIR`.

    In production `BASE_DIR` is the **read-only Nix store** -- which is exactly why the database is
    not there either but under `/var/lib/demockrazy` (notes/deployment.md). The lock file follows
    the database, and then writability takes care of itself.

    With an in-memory database (the test suite) there is no place next to it; the temp directory
    then.
    """
    name = str(settings.DATABASES["default"]["NAME"] if database_name is None else database_name)
    if name.startswith(":") or "mode=memory" in name:
        return Path(tempfile.gettempdir()) / "demockrazy-mailsend.lock"
    return Path(name).with_suffix(".mailsend.lock")


class Command(BaseCommand):
    help = "Verschickt wartende Umfrage-Mails in Batches mit Pause dazwischen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=None,
            help="Nachrichten pro Batch (Default: settings.VOTE_MAIL_BATCH_SIZE).",
        )
        parser.add_argument(
            "--pause",
            type=float,
            default=None,
            help="Sekunden zwischen zwei Batches (Default: settings.VOTE_MAIL_BATCH_PAUSE).",
        )

    def handle(self, *args, **options):
        handle = lock_path().open("w")
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                # No error and no non-zero exit code: the timer firing into a run that is already
                # going is the normal case and should not show up in the journal as a failure.
                self.stdout.write("Es läuft schon ein Versand, dieser Aufruf tut nichts.")
                return
            summary = mail.send_pending(batch_size=options["batch_size"], pause=options["pause"])
        finally:
            # Closes the descriptor and with it the flock.
            handle.close()

        self.stdout.write(
            "{sent} verschickt, {given_up} aufgegeben, {remaining} warten noch "
            "({batches} Batches).".format(**summary)
        )
