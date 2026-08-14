"""How far does a transaction reach? (plan B16)

From 2016 to 2026 `demockrazy/settings.py` carried a module-wide `ATOMIC_REQUESTS = True`. Django
reads the option **per database**, so the value was never in effect. These tests record the actual
state, so that nobody has to infer it from a comment again.

What carries atomicity instead is tested where it lives and not repeated here:
`vote/tests/test_poll_service.py::test_rolls_back_as_a_whole` for creating a poll,
`vote/tests/test_views.py::test_incomplete_answer_rolls_everything_back` for casting a vote. Both
were green while this option did nothing -- that is the evidence.
"""

from django.core.handlers.base import BaseHandler
from django.db import connections
from django.urls import resolve


def test_requests_are_not_wrapped_in_a_transaction():
    """If this goes red, someone really did switch `ATOMIC_REQUESTS` on.

    That would not be a mistake, but a decision to be made rather than inherited: on SQLite with
    four uwsgi processes every request then takes a transaction, the plain results page included
    (B13). The reasoning and open question F18 are in demockrazy/settings.py.
    """
    assert connections.settings["default"]["ATOMIC_REQUESTS"] is False


def test_django_wraps_no_view():
    """The counter-check to the settings value, one step closer to the behaviour.

    `make_view_atomic()` is the place that evaluates the option; it returns the view unchanged as
    long as no transaction is put around the request. Without this test the one above would only be
    a statement about a dictionary.
    """
    handler = BaseHandler()
    for path in ("/vote/", "/vote/create"):
        view = resolve(path).func
        assert handler.make_view_atomic(view) is view, path
