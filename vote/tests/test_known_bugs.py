"""Die in Phase 0 bestätigten Bugs, formuliert als das gewünschte Verhalten.

**Derzeit steht hier kein `xfail` mehr** -- alle Bugs, die diese Datei beschreibt, sind behoben, und
die Tests stehen ohne Marker als Regressionstests. Die Nummern (B2, B3, ...) bleiben als Verweis auf
notes/plan.md §2 erhalten.

Das Muster für den nächsten Bug ist trotzdem dieses: `xfail(strict=True)`, der Test beschreibt, was
passieren *soll*, und schlägt heute fehl. Sobald jemand ihn behebt, wird er zu einem unerwarteten
Erfolg -- was die Suite rot macht und daran erinnert, den Marker zu entfernen.

Merke aus 3.8: mit dem Marker kann auch die *Erwartung* fallen. Der B4-Test verlangte einen
ablehnenden Statuscode, solange die Schutzmaßnahme offen war; ein Deckel im Formular ergibt einen
200 mit Fehlermeldung. Geprüft wird jetzt die Wirkung, nicht der Statuscode.

Behoben: B3, B6, B11, B12 (Plan 3.2) · B2 (Plan 3.3) · die zwei Unique-Constraints (Plan 3.6) ·
B4 (Plan 3.8) · B10 (Plan 4.2) · B9 (Plan 3.9). Damit ist das Register vollstaendig abgearbeitet.
B15 ist erst in 3.3 aufgefallen und sofort behoben worden, hatte also nie einen Marker -- die
Regressionstests dazu stehen in test_views.py bei den übrigen Stimmabgabe-Tests.
"""

import json

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


@pytest.mark.django_db
def test_b2_vote_without_token_field_shows_an_error(lenient_client, create_poll):
    """Fehlt das Token-Feld ganz, soll eine Fehlermeldung erscheinen, kein UnboundLocalError."""
    poll, _ = create_poll()
    response = lenient_client.post(
        f"/vote/{poll.identifier}/vote", {"choice": poll.choice_set.first().id}
    )
    assert response.status_code != 500
    assert response.context["error_message"] == "invalid token."
    assert poll.choice_set.first().votes == 0, "ohne Token darf keine Stimme gezählt werden"
    assert poll.token_set.count() == 2, "und kein Token verbraucht werden"


@pytest.mark.django_db
def test_b11_manage_without_token_field_shows_an_error(lenient_client, create_poll):
    poll, _ = create_poll()
    response = lenient_client.post(f"/vote/{poll.identifier}/manage", {})
    assert response.status_code != 500
    assert response.context["error_message"] == "Wrong management token"
    poll.refresh_from_db()
    assert poll.is_active is True, "eine Umfrage ohne Token darf nicht geschlossen werden"


@pytest.mark.django_db
def test_b4_poll_creation_is_not_wide_open(client, mailoutbox):
    """Ein anonymer Request darf nicht beliebig viele Mails ueber den SMTP-Server verschicken.

    F5 ist entschieden: ein Deckel auf die Empfaengerzahl, kein IP-Rate-Limit (Plan 3.8).

    **Die Erwartung hat sich mit der Entscheidung geaendert.** Solange die Massnahme offenstand,
    verlangte dieser Test einen ablehnenden Statuscode (400/401/403/429). Ein Deckel im Formular
    ergibt aber einen 200 mit Fehlermeldung -- wie jede andere ungueltige Eingabe auch, und aus
    demselben Grund: der Ersteller soll seine Liste zurueckbekommen und kuerzen koennen, nicht in
    einer Sackgasse landen (Plan 3.2). Gepruefte Zusage ist deshalb nicht der Code, sondern die
    Wirkung: es entsteht keine Umfrage und es geht keine Mail raus.
    """
    response = client.post(
        "/vote/create",
        _create_payload(voter_mails="\n".join(f"opfer{i}@example.org" for i in range(500))),
    )
    assert response.status_code == 200
    assert not Poll.objects.filter(title="Bugtest").exists()
    assert mailoutbox == [], "auch nicht an den Ersteller"
    assert "At most 150 recipients" in response.content.decode()


@pytest.mark.django_db
def test_b10_special_characters_survive_into_the_chart(client):
    """Der Text im Diagramm muss der Text sein, den der Ersteller eingetippt hat.

    Vorher stand `name: '{{ choice.choice_text }}'` in einem JS-Stringliteral. Django escapte fuers
    HTML, aber der Inhalt eines <script>-Elements wird nicht entity-dekodiert -- aus `Bier & Brezn`
    wurde im Diagramm sichtbar `Bier &amp; Brezn`. Gemessen, nicht vermutet: das galt fuer `&`, `'`,
    `"` und `<`.
    """
    poll = Poll.objects.create(title="P", question_text="?", num_tokens=0, is_active=False)
    texts = ["Bier & Brezn", "Annas 'Wahl'", "<b>fett</b>", 'Anfuehrung "so"']
    for text in texts:
        poll.choice_set.create(choice_text=text, votes=1)

    content = client.get(f"/vote/{poll.identifier}/results").content.decode()
    payload = content.split('id="chart-series"')[1].split("</script>")[0]
    series = json.loads(payload.split(">", 1)[1])

    assert [entry["name"] for entry in series][: len(texts)] == texts
    # Und die Gegenprobe zum eigentlichen Zweck von json_script: kein `</script>` bricht aus.
    assert "</script>" not in payload.split(">", 1)[1]


@pytest.mark.django_db
def test_b9_the_browser_does_not_keep_the_token_in_the_url(client, create_poll):
    """Auf der Adresse, auf der der Browser stehen bleibt, darf kein Token stehen.

    `?token=…` war das einzige Auth-Merkmal und stand damit im nginx-Access-Log, in der
    Browser-History und -- weil die Referrer-Policy fuer gleichherkuenftige Anfragen die
    vollstaendige URL sendet -- im `Referer` jeder Anfrage, die die Seite ausloest, also auch in
    jeder Logzeile ueber ein Stylesheet.

    Die Behebung ist **additiv** (Regel 4/5): der Link in der Mail bleibt zeichengleich, der Token
    zieht beim ersten Aufruf in ein Cookie um. **Was offen bleibt und offen bleiben muss:** die
    Logzeile dieses *einen* Aufrufs. Sie haengt an einem klickbaren Link und ist nur am Proxy zu
    loesen (`log_format` ohne `$args`) -- siehe notes/to-check.md.

    Die Mechanik des Umzugs steht in test_views.py::TestTokenLeavesTheUrl.
    """
    poll, tokens = create_poll()
    response = client.get(f"/vote/{poll.identifier}/", {"token": tokens[0]}, follow=True)

    final_url, status = response.redirect_chain[-1]
    assert status == 302
    assert tokens[0] not in final_url
    assert "token" not in final_url
    # Und die Seite ist trotzdem die richtige: der Token steht im Formular, nur nicht in der URL.
    assert response.status_code == 200
    assert response.context["token"] == tokens[0]


@pytest.mark.django_db
def test_token_string_is_unique():
    """Seit 3.6 erzwingt die Datenbank das, statt sich auf eine Vorabpruefung zu verlassen."""
    from django.db import IntegrityError

    poll = Poll.objects.create(title="P", question_text="?")
    Token.objects.create(poll=poll, token_string="derselbe")
    with pytest.raises(IntegrityError):
        Token.objects.create(poll=poll, token_string="derselbe")


@pytest.mark.django_db
def test_poll_identifier_is_unique():
    from django.db import IntegrityError

    Poll.objects.create(title="A", question_text="?", identifier="dieselbe")
    with pytest.raises(IntegrityError):
        Poll.objects.create(title="B", question_text="?", identifier="dieselbe")
