"""Tests für vote/services/polls.py (Plan 3.5)."""

import pytest

from vote.models import Choice, Poll, Token
from vote.services import polls

pytestmark = pytest.mark.django_db


def create(**overrides):
    kwargs = {
        "title": "Testabstimmung",
        "poll_type": "simple_choice",
        "question_text": "Wollen wir das?",
        "choices": ["Ja", "Nein"],
        "num_tokens": 2,
    }
    kwargs.update(overrides)
    return polls.create_poll(**kwargs)


class TestCreatePoll:
    def test_creates_the_poll(self):
        poll, _ = create()
        assert poll.title == "Testabstimmung"
        assert poll.type == "simple_choice"
        assert poll.question_text == "Wollen wir das?"
        assert poll.num_tokens == 2
        assert poll.is_active is True

    def test_creates_the_choices_in_input_order(self):
        poll, _ = create(choices=["Ja", "Nein", "Vielleicht"])
        assert list(poll.choice_set.values_list("choice_text", flat=True)) == [
            "Ja",
            "Nein",
            "Vielleicht",
        ]

    def test_creates_one_token_per_recipient(self):
        poll, tokens = create(num_tokens=5)
        assert len(tokens) == 5
        assert poll.token_set.count() == 5

    def test_tokens_are_distinct_and_have_the_expected_length(self):
        _, tokens = create(num_tokens=5)
        strings = [token.token_string for token in tokens]
        assert len(set(strings)) == 5
        assert {len(s) for s in strings} == {128}

    def test_returned_tokens_are_the_persisted_ones(self):
        """bulk_create liefert auf SQLite die Primärschlüssel mit zurück (RETURNING)."""
        _, tokens = create(num_tokens=3)
        assert all(token.pk is not None for token in tokens)
        assert set(Token.objects.values_list("pk", flat=True)) == {t.pk for t in tokens}

    def test_no_recipients_means_no_tokens(self):
        poll, tokens = create(num_tokens=0)
        assert tokens == []
        assert poll.token_set.count() == 0

    def test_rolls_back_as_a_whole(self, monkeypatch):
        """Die Funktion ist atomar, damit sie auch außerhalb eines Requests nichts halb anlegt.

        Der Fehler wird beim Anlegen der Tokens ausgelöst, also nachdem Umfrage und Choices
        schon in der Datenbank stehen -- genau der Zustand, der nicht überleben darf.
        """

        def boom(*args, **kwargs):
            raise RuntimeError("Datenbank weg")

        monkeypatch.setattr(Token.objects, "bulk_create", boom)
        with pytest.raises(RuntimeError):
            create()
        assert not Poll.objects.exists()
        assert not Choice.objects.exists()
        assert not Token.objects.exists()


class TestQueryCount:
    """Der Punkt von 3.5 und 3.6: die Zahl der Statements hängt nicht an der Umfragegröße.

    2 Savepoint-Statements (`transaction.atomic`) + 3 INSERT (Umfrage, Choices, Tokens).
    Kein SELECT mehr: 3.5 hat aus den Save-Schleifen zwei `bulk_create` gemacht, 3.6 hat die
    Kollisionsprüfungen in `mk_identifier`/`mk_token` gestrichen -- die Eindeutigkeit erzwingt
    jetzt der `UniqueConstraint`. Vor 3.5 waren es bei 200 Empfängern 404 Queries.
    """

    EXPECTED = 5

    @pytest.mark.parametrize(
        ("num_choices", "num_tokens"), [(2, 2), (50, 2), (2, 50), (50, 50), (2, 200)]
    )
    def test_is_constant(self, django_assert_num_queries, num_choices, num_tokens):
        with django_assert_num_queries(self.EXPECTED):
            create(choices=[f"c{i}" for i in range(num_choices)], num_tokens=num_tokens)
