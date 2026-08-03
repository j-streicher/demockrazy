"""Die in Phase 0 bestätigten Bugs, formuliert als das gewünschte Verhalten.

Ein noch offener Bug steht hier mit `xfail(strict=True)`: der Test beschreibt, was passieren
*soll*, und schlägt heute fehl. Sobald Phase 3 ihn behebt, wird er zu einem unerwarteten Erfolg --
was die Suite rot macht und daran erinnert, den Marker zu entfernen.

Behobene Bugs bleiben ohne Marker stehen und sind ab dann Regressionstests. Die Nummern
(B2, B3, ...) bleiben als Verweis auf notes/plan.md §2 erhalten.

Behoben: B3, B6, B11, B12 (Plan 3.2).
"""

import pytest
from django.test import Client

from vote.models import Poll, Token

from .conftest import CREATOR_MAIL


@pytest.fixture
def lenient_client():
    """Liefert bei einer Exception einen 500 statt sie durchzureichen.

    Hier interessiert, welche *Antwort* der Nutzer bekommt, nicht der Traceback.
    """
    return Client(raise_request_exception=False)


def _create_payload(**overrides):
    payload = {
        "title": "Bugtest",
        "type": "simple_choice",
        "description": "?",
        "choices": "Ja\nNein",
        "creator_mail": CREATOR_MAIL,
        "voter_mails": "a@example.org\nb@example.org",
    }
    payload.update(overrides)
    return payload


@pytest.mark.django_db
def test_b3_get_on_create_does_not_crash(lenient_client):
    """GET /vote/create soll das Formular zeigen oder umleiten, nicht mit 500 sterben."""
    response = lenient_client.get("/vote/create")
    assert response.status_code != 500


@pytest.mark.django_db
def test_b3_invalid_poll_type_is_a_form_error(lenient_client):
    """Ein unbekannter type soll als Formularfehler zurueckkommen, nicht als 500."""
    response = lenient_client.post("/vote/create", _create_payload(type="quatsch"))
    assert response.status_code != 500
    assert not Poll.objects.filter(title="Bugtest").exists()


@pytest.mark.django_db
def test_b12_invalid_mail_address_is_a_form_error(lenient_client):
    """Eine kaputte Adresse soll eine Fehlermeldung erzeugen und keine Umfrage anlegen."""
    response = lenient_client.post(
        "/vote/create", _create_payload(voter_mails="gueltig@example.org\nKAPUTT")
    )
    assert response.status_code != 500
    assert not Poll.objects.filter(title="Bugtest").exists()


@pytest.mark.django_db
def test_b6_duplicate_addresses_get_one_token_each(client):
    """Dieselbe Adresse dreimal eingetragen darf nicht drei Stimmrechte ergeben."""
    client.post("/vote/create", _create_payload(voter_mails="dup@example.org\n" * 3))
    poll = Poll.objects.get(title="Bugtest")
    assert poll.num_tokens == 1
    assert poll.token_set.count() == 1


@pytest.mark.xfail(
    strict=True, reason="B2: token_string wird im except-Zweig vor der Zuweisung gelesen"
)
@pytest.mark.django_db
def test_b2_vote_without_token_field_shows_an_error(lenient_client, create_poll):
    """Fehlt das Token-Feld ganz, soll eine Fehlermeldung erscheinen, kein UnboundLocalError."""
    poll, _ = create_poll()
    response = lenient_client.post(
        f"/vote/{poll.identifier}/vote", {"choice": poll.choice_set.first().id}
    )
    assert response.status_code != 500


@pytest.mark.django_db
def test_b11_manage_without_token_field_shows_an_error(lenient_client, create_poll):
    poll, _ = create_poll()
    response = lenient_client.post(f"/vote/{poll.identifier}/manage", {})
    assert response.status_code != 500
    assert response.context["error_message"] == "Wrong management token"
    poll.refresh_from_db()
    assert poll.is_active is True, "eine Umfrage ohne Token darf nicht geschlossen werden"


@pytest.mark.xfail(strict=True, reason="B4: create() ist unauthentifiziert und ohne Rate-Limit")
@pytest.mark.django_db
def test_b4_poll_creation_is_not_wide_open(lenient_client):
    """Ein anonymer Request darf nicht beliebig viele Mails ueber den SMTP-Server verschicken.

    Bewusst grob formuliert -- die konkrete Schutzmassnahme steht noch nicht fest (Plan F5).
    Der Test haelt nur fest, dass es ueberhaupt eine geben muss.
    """
    response = lenient_client.post(
        "/vote/create",
        _create_payload(voter_mails="\n".join(f"opfer{i}@example.org" for i in range(500))),
    )
    assert response.status_code in (400, 401, 403, 429)


@pytest.mark.xfail(strict=True, reason="3.6: token_string hat keinen UNIQUE-Constraint")
@pytest.mark.django_db
def test_token_string_is_unique():
    """mk_token() prueft auf Kollisionen, die Datenbank erzwingt es aber nicht."""
    from django.db import IntegrityError

    poll = Poll.objects.create(title="P", question_text="?")
    Token.objects.create(poll=poll, token_string="derselbe")
    with pytest.raises(IntegrityError):
        Token.objects.create(poll=poll, token_string="derselbe")


@pytest.mark.xfail(strict=True, reason="3.6: identifier hat keinen UNIQUE-Constraint")
@pytest.mark.django_db
def test_poll_identifier_is_unique():
    from django.db import IntegrityError

    Poll.objects.create(title="A", question_text="?", identifier="dieselbe")
    with pytest.raises(IntegrityError):
        Poll.objects.create(title="B", question_text="?", identifier="dieselbe")
