"""A fake SMTP server that accepts, records, and throttles like a real one.

Used two ways: as the counterpart of the one test that speaks SMTP over a socket, and by hand while
checking delivery -- `python3 -m vote.tests.mailtrap [limit] [port]`, then point `EMAIL_HOST`/
`EMAIL_PORT` at it in `local_settings.py` (with `EMAIL_USE_TLS = False`; the default is True and a
fake server speaks no STARTTLS).

Deliberately dependency-free: `smtpd` left the standard library in Python 3.12, so the classic
`python -m smtpd -n -c DebuggingServer` is gone.
"""

import socketserver
import sys
import threading

END_OF_DATA = (b".\r\n", b".\n", b"")


class _Handler(socketserver.StreamRequestHandler):
    """One SMTP conversation. Only what a client needs to get a message in is modelled."""

    def _reply(self, line):
        self.wfile.write(line.encode() + b"\r\n")
        self.wfile.flush()

    def handle(self):
        self._reply("220 fake.invalid ESMTP")
        recipients = []
        while line := self.rfile.readline():
            command = line.decode("utf-8", "replace").strip()
            verb = command.upper()
            if verb.startswith("EHLO"):
                self._reply("250-fake.invalid")
                self._reply("250 HELP")
            elif verb.startswith("RCPT TO"):
                recipients.append(command.split("<")[-1].rstrip(">"))
                self._reply("250 OK")
            elif verb == "DATA":
                self._reply("354 End data with <CR><LF>.<CR><LF>")
                self._reply(self.server.deliver(recipients, self._read_body()))
                recipients = []
            elif verb == "QUIT":
                self._reply("221 Bye")
                return
            else:
                # MAIL FROM, HELO, RSET, NOOP -- nothing here depends on their arguments.
                self._reply("250 OK")

    def _read_body(self):
        """The subject line, for the hand-driven log. The rest of the body is read and dropped."""
        subject = ""
        while (line := self.rfile.readline()) not in END_OF_DATA:
            if line.startswith(b"Subject:"):
                subject = line.decode("utf-8", "replace").strip()
        return subject


class MailTrap(socketserver.ThreadingTCPServer):
    """Answers `250` until `limit` messages have arrived, then `450` -- the shape of throttling.

    `limit=0` never throttles. `port=0` picks a free port, which is what the test wants; `.port`
    reports it. Serving happens on a thread, so use it as a context manager.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, limit=0, port=0, verbose=False):
        super().__init__(("127.0.0.1", port), _Handler)
        self.limit = limit
        self.verbose = verbose
        self.accepted = []
        self.throttled = []
        self._lock = threading.Lock()

    @property
    def port(self):
        return self.server_address[1]

    def deliver(self, recipients, subject=""):
        """Records one message and returns the reply it gets. Called from a handler thread."""
        with self._lock:
            count = len(self.accepted) + len(self.throttled) + 1
            over_limit = bool(self.limit) and count > self.limit
            (self.throttled if over_limit else self.accepted).extend(recipients)
        if over_limit:
            self._log(f"[{count:3d}] 450 throttled    {recipients}")
            return "450 4.7.1 Error: too much mail from <fake>"
        self._log(f"[{count:3d}] 250 {(recipients or ['?'])[0]:26s} {subject[:58]}")
        return "250 OK: queued"

    def _log(self, line):
        if self.verbose:
            print(line, flush=True)

    def __enter__(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc_info):
        self.shutdown()
        self.server_close()


def main(argv):
    limit = int(argv[0]) if argv else 30
    port = int(argv[1]) if len(argv) > 1 else 1025
    with MailTrap(limit=limit, port=port, verbose=True) as trap:
        print(
            f"fake SMTP on 127.0.0.1:{trap.port}, throttling from message {limit or '(never)'}",
            flush=True,
        )
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("")


if __name__ == "__main__":
    main(sys.argv[1:])
