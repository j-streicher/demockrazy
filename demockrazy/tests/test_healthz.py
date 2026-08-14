"""Tests for the operational endpoint from demockrazy/views.py (plan 5.5)."""

import pytest
from django.db.utils import OperationalError
from django.urls import resolve

from demockrazy import views


@pytest.mark.django_db
class TestHealthz:
    def test_reports_ok(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.content == b"ok\n"
        assert response.headers["Content-Type"] == "text/plain"

    def test_head_works_too(self, client):
        """Some probers send HEAD. `require_safe` lets GET and HEAD through."""
        assert client.head("/healthz").status_code == 200

    def test_rejects_write_methods(self, client):
        assert client.post("/healthz").status_code == 405

    def test_reports_503_without_leaking_why(self, client, monkeypatch, caplog):
        """The endpoint is unauthenticated -- the file path must not appear in the response."""

        path = "/var/lib/demockrazy/db.sqlite3"

        class UnreadableDatabase:
            def cursor(self):
                raise OperationalError(f"unable to open database file: {path}")

            # Django closes the connection at the end of the request.
            def close(self):
                pass

        monkeypatch.setattr(views, "connection", UnreadableDatabase())
        response = client.get("/healthz")

        assert response.status_code == 503
        assert response.content == b"database unavailable\n"
        assert b"/var/lib/demockrazy" not in response.content
        assert "unable to open database file" in caplog.text


def test_declares_itself_non_atomic():
    """Deliberately checking the declaration, not the behaviour.

    Today no view has a transaction around it (B16), so a behaviour test would be green for the
    wrong reason -- see test_transactions.py. What is recorded here is the intent: if
    `ATOMIC_REQUESTS` is ever switched on (F18), this endpoint stays exempt.
    """
    view = resolve("/healthz").func
    assert "default" in getattr(view, "_non_atomic_requests", set())
