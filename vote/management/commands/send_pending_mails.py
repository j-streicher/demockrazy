"""Verschickt die Mail-Warteschlange getaktet. Für einen systemd-Timer gedacht.

Der Command ist bewusst dünn: die Arbeit steckt in `vote.services.mail.send_pending()`, hier stehen
nur die Betriebsdinge -- Optionen, die **Sperre** und eine Zusammenfassung nach stdout.

Warum eine eigene Sperre und nicht das Verlassen auf systemd: ein Lauf dauert Minuten (30 Mails,
dann 2 s, dann die nächsten), der Timer feuert aber im Minutentakt. Zwei gleichzeitige Läufe würden
dieselben Zeilen greifen und doppelt verschicken. `flock` macht das unmöglich, egal wie der Command
gestartet wird -- auch bei einem Aufruf von Hand, während der Timer arbeitet.
"""

import fcntl
import tempfile
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from vote.services import mail


def lock_path(database_name=None):
    """Die Sperrdatei liegt neben der Datenbank, nicht unter `BASE_DIR`.

    `BASE_DIR` ist in Produktion der **read-only Nix-Store** -- genau deshalb liegt auch die
    Datenbank dort nicht, sondern unter `/var/lib/demockrazy` (notes/deployment.md). Die
    Sperrdatei folgt der Datenbank, dann stimmt die Schreibbarkeit automatisch.

    Bei einer In-Memory-Datenbank (Testsuite) gibt es keinen Ort daneben; dann das Temp-Verzeichnis.
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
                # Kein Fehler und kein Rückgabecode ungleich 0: dass der Timer in einen laufenden
                # Versand feuert, ist der Normalfall und soll nicht als Fehlschlag im Journal
                # stehen.
                self.stdout.write("Es läuft schon ein Versand, dieser Aufruf tut nichts.")
                return
            summary = mail.send_pending(batch_size=options["batch_size"], pause=options["pause"])
        finally:
            # Schließt den Deskriptor und damit auch die flock-Sperre.
            handle.close()

        self.stdout.write(
            "{sent} verschickt, {given_up} aufgegeben, {remaining} warten noch "
            "({batches} Batches).".format(**summary)
        )
