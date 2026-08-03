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
    """Der Punkt von 3.5: die Zahl der Statements wächst nicht mehr mit der Umfragegröße."""

    def test_choices_cost_one_insert_no_matter_how_many(self, django_assert_num_queries):
        with django_assert_num_queries(8):
            create(choices=[f"c{i}" for i in range(2)])
        with django_assert_num_queries(8):
            create(choices=[f"c{i}" for i in range(50)])

    def test_tokens_cost_one_insert_no_matter_how_many(self, django_assert_num_queries):
        """Ein INSERT für alle Tokens -- die Queries, die bleiben, sind SELECTs.

        `mk_token()` fragt pro Token einmal nach einer Kollision. Das ist der Rest, der noch
        linear wächst; er verschwindet mit dem UniqueConstraint aus 3.6, der die Prüfung
        überflüssig macht. Deshalb hier als Formel und nicht als nackte Zahl.
        """
        for num_tokens in (2, 20):
            # 2 Savepoint-Statements (transaction.atomic) + 1 SELECT mk_identifier
            # + 3 INSERT (Umfrage, Choices, Tokens) + 1 SELECT je mk_token.
            with django_assert_num_queries(6 + num_tokens):
                create(num_tokens=num_tokens)
