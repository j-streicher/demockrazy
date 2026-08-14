"""A fake SMTP server that accepts, records, and throttles like a real one.

Used two ways: as the counterpart of the one test that speaks SMTP over a socket, and by hand while
checking delivery -- `python3 -m vote.tests.mailtrap [limit] [window] [port]`, then point
`EMAIL_HOST`/`EMAIL_PORT` at it in `local_settings.py` (with `EMAIL_USE_TLS = False`; the default is
True and a fake server speaks no STARTTLS).

Deliberately dependency-free: `smtpd` left the standard library in Python 3.12, so the classic
`python -m smtpd -n -c DebuggingServer` is gone.
"""

import socketserver
import sys
import threading
import time

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
    """Answers `250` until `limit` messages have arrived inside `window`, then `450`.

    `limit=0` never throttles. **`window` is what makes this behave like a real server** (R15-2): a
    mail server throttles per *time window*, so its refusal lapses when the window does. `window=0`
    means the counter never resets -- right for a test, wrong for anything driven by hand, where the
    point is watching the next run get through.

    `port=0` picks a free port, which is what a test wants; `.port` reports it. `clock` is
    injectable so a test can drive the window without waiting on the wall clock. Serving happens on
    a thread, so use it as a context manager.
    """

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, limit=0, window=0, port=0, verbose=False, clock=time.monotonic):
        super().__init__(("127.0.0.1", port), _Handler)
        self.limit = limit
        self.window = window
        self.verbose = verbose
        self.accepted = []
        self.throttled = []
        self._clock = clock
        self._window_started = clock()
        self._in_window = 0
        self._lock = threading.Lock()

    @property
    def port(self):
        return self.server_address[1]

    def deliver(self, recipients, subject=""):
        """Records one message and returns the reply it gets. Called from a handler thread."""
        with self._lock:
            now = self._clock()
            if self.window and now - self._window_started >= self.window:
                self._window_started, self._in_window = now, 0
            self._in_window += 1
            count = len(self.accepted) + len(self.throttled) + 1
            over_limit = bool(self.limit) and self._in_window > self.limit
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
    # 60 s by default because that is Postfix's own counting window (F20) and the interval the
    # systemd timer runs on: a second run then finds the window reset, exactly as in production.
    window = float(argv[1]) if len(argv) > 1 else 60.0
    port = int(argv[2]) if len(argv) > 2 else 1025
    with MailTrap(limit=limit, window=window, port=port, verbose=True) as trap:
        print(
            f"fake SMTP on 127.0.0.1:{trap.port}, throttling past "
            f"{limit or '(never)'} messages per {window:g} s",
            flush=True,
        )
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            print("")


if __name__ == "__main__":
    main(sys.argv[1:])
