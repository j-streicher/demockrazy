"""Tests für den Betriebs-Endpunkt aus demockrazy/views.py (Plan 5.5)."""

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
        """Manche Prober schicken HEAD. `require_safe` lässt GET und HEAD durch."""
        assert client.head("/healthz").status_code == 200

    def test_rejects_write_methods(self, client):
        assert client.post("/healthz").status_code == 405

    def test_reports_503_without_leaking_why(self, client, monkeypatch, caplog):
        """Der Endpunkt ist unauthentifiziert -- der Dateipfad darf nicht in der Antwort stehen."""

        path = "/var/lib/demockrazy/db.sqlite3"

        class UnreadableDatabase:
            def cursor(self):
                raise OperationalError(f"unable to open database file: {path}")

            # Django schließt die Verbindung am Ende des Requests.
            def close(self):
                pass

        monkeypatch.setattr(views, "connection", UnreadableDatabase())
        response = client.get("/healthz")

        assert response.status_code == 503
        assert response.content == b"database unavailable\n"
        assert b"/var/lib/demockrazy" not in response.content
        assert "unable to open database file" in caplog.text


def test_declares_itself_non_atomic():
    """Bewusst die Deklaration prüfen, nicht das Verhalten.

    Heute ist um keine View eine Transaktion gelegt (B16), ein Verhaltenstest wäre also aus dem
    falschen Grund grün -- siehe test_transactions.py. Was hier festgehalten wird, ist die Absicht:
    falls `ATOMIC_REQUESTS` je eingeschaltet wird (F18), bleibt dieser Endpunkt ausgenommen.
    """
    view = resolve("/healthz").func
    assert "default" in getattr(view, "_non_atomic_requests", set())
