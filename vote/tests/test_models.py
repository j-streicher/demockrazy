"""Tests fuer vote/models.py: Token-Erzeugung und die Zaehlerlogik."""

import string

import pytest

from vote.models import Choice, Poll, Token, mk_admin_token, mk_identifier, mk_token, rand_string

ALLOWED = set(string.ascii_letters + string.digits)


class TestRandString:
    def test_length(self):
        assert len(rand_string(17)) == 17

    def test_charset(self):
        assert set(rand_string(500)) <= ALLOWED

    def test_not_constant(self):
        assert rand_string(64) != rand_string(64)


@pytest.mark.django_db
class TestTokenGeneration:
    """Die Längen sind Teil des Datenmodells (max_length) und dürfen sich nicht ändern."""

    def test_identifier_length(self):
        assert len(mk_identifier()) == 64

    def test_token_length(self):
        assert len(mk_token()) == 128

    def test_admin_token_length(self):
        assert len(mk_admin_token()) == 256


@pytest.mark.django_db
class TestStr:
    def test_poll(self):
        assert str(Poll(title="Kantinenwahl")) == "Kantinenwahl"

    def test_choice(self):
        poll = Poll.objects.create(title="Kantinenwahl", question_text="?")
        choice = Choice.objects.create(poll=poll, choice_text="Pizza")
        assert str(choice) == "Kantinenwahl - Pizza"

    def test_token(self):
        poll = Poll.objects.create(title="Kantinenwahl", question_text="?")
        assert str(Token.objects.create(poll=poll)) == "Kantinenwahl Token"


@pytest.mark.django_db
class TestGetAmountUsedUnused:
    """Liefert (eingelöst, offen, gesamt).

    Zwei Pfade: mit gesetztem num_tokens wird von der Gesamtzahl heruntergerechnet, ohne
    (Alt-Umfragen ohne Empfängerliste) über die Summe der Stimmen.
    """

    def test_nothing_redeemed_yet(self):
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=3)
        for _ in range(3):
            Token.objects.create(poll=poll)
        assert poll.get_amount_used_unused() == (0, 3, 3)

    def test_partially_redeemed(self):
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=3)
        Token.objects.create(poll=poll)
        assert poll.get_amount_used_unused() == (2, 1, 3)

    def test_fully_redeemed(self):
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=3)
        assert poll.get_amount_used_unused() == (3, 0, 3)

    def test_without_num_tokens_counts_votes(self):
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=None)
        Choice.objects.create(poll=poll, choice_text="A", votes=3)
        Token.objects.create(poll=poll)
        assert poll.get_amount_used_unused() == (3, 1, 4)

    def test_without_num_tokens_sums_all_choices(self):
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=None)
        Choice.objects.create(poll=poll, choice_text="A", votes=2)
        Choice.objects.create(poll=poll, choice_text="B", votes=5)
        assert poll.get_amount_used_unused() == (7, 0, 7)


@pytest.mark.django_db
class TestDefaults:
    def test_poll_defaults(self):
        poll = Poll.objects.create(title="P", question_text="?")
        assert poll.is_active is True
        assert poll.type == "simple_choice"
        assert poll.pub_date is not None
        assert len(poll.identifier) == 64
        assert len(poll.creator_token) == 256

    def test_choice_starts_at_zero_votes(self):
        poll = Poll.objects.create(title="P", question_text="?")
        assert Choice.objects.create(poll=poll, choice_text="A").votes == 0

    def test_deleting_poll_cascades(self):
        poll = Poll.objects.create(title="P", question_text="?")
        Choice.objects.create(poll=poll, choice_text="A")
        Token.objects.create(poll=poll)
        poll.delete()
        assert Choice.objects.count() == 0
        assert Token.objects.count() == 0
