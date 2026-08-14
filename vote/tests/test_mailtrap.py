"""Tests for the fake SMTP server in vote/tests/mailtrap.py.

It is test infrastructure and still gets tested, because that is the lesson of R10-4: a double that
is more lenient than the real server hides exactly the failures it exists for. So these tests hold
the trap against what it claims -- that it throttles per time window (R15-2).

No test here waits on the wall clock: the window is driven through an injected clock.
"""

import smtplib

from vote.tests.mailtrap import MailTrap


class FakeClock:
    """A clock a test can move. Passed to `MailTrap(clock=...)`."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def send(port, recipient="a@example.org"):
    """Sends one message and returns the SMTP code, or the code of the refusal."""
    with smtplib.SMTP("127.0.0.1", port, timeout=5) as smtp:
        try:
            smtp.sendmail("from@example.org", [recipient], f"Subject: s\n\nto {recipient}")
            return 250
        except smtplib.SMTPResponseException as error:
            return error.smtp_code


class TestTheThrottlingWindow:
    """R15-2: a real server's refusal lapses with its window, and so must the trap's.

    Before this, the counter ran for the lifetime of the process. Measured consequence: the second
    `send_pending_mails` run against the same trap sent nothing (0 of 3), and the tenth run gave up
    on the invitation and deleted it -- so the instructions in README and handover demonstrated the
    opposite of what they were for.
    """

    def test_the_limit_bites_inside_the_window(self):
        clock = FakeClock()
        with MailTrap(limit=1, window=10, clock=clock) as trap:
            assert send(trap.port) == 250
            assert send(trap.port) == 450

    def test_the_refusal_lapses_when_the_window_does(self):
        clock = FakeClock()
        with MailTrap(limit=1, window=10, clock=clock) as trap:
            assert send(trap.port) == 250
            assert send(trap.port) == 450
            clock.advance(10)
            assert send(trap.port) == 250, "the window has passed, so the next message gets through"

    def test_a_window_that_has_not_passed_still_refuses(self):
        clock = FakeClock()
        with MailTrap(limit=1, window=10, clock=clock) as trap:
            assert send(trap.port) == 250
            clock.advance(9.9)
            assert send(trap.port) == 450

    def test_without_a_window_the_refusal_never_lapses(self):
        """`window=0` is the setting a test wants: no clock, no lapsing, nothing to wait for."""
        clock = FakeClock()
        with MailTrap(limit=1, window=0, clock=clock) as trap:
            assert send(trap.port) == 250
            clock.advance(10_000)
            assert send(trap.port) == 450

    def test_the_counters_keep_the_whole_run_not_just_the_window(self):
        """The window resets the *throttling* counter only -- assertions rely on the full record."""
        clock = FakeClock()
        with MailTrap(limit=1, window=10, clock=clock) as trap:
            send(trap.port, "one@example.org")
            send(trap.port, "two@example.org")
            clock.advance(10)
            send(trap.port, "three@example.org")
        assert trap.accepted == ["one@example.org", "three@example.org"]
        assert trap.throttled == ["two@example.org"]

    def test_no_limit_means_no_throttling_whatever_the_window(self):
        clock = FakeClock()
        with MailTrap(limit=0, window=10, clock=clock) as trap:
            assert [send(trap.port) for _ in range(5)] == [250] * 5
