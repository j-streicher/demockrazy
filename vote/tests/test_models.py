"""Tests fuer vote/models.py: Token-Erzeugung und die Zaehlerlogik."""

import random
import string

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from vote.models import (
    Choice,
    Poll,
    PollType,
    Token,
    mk_admin_token,
    mk_identifier,
    mk_token,
    rand_string,
)

ALLOWED = set(string.ascii_letters + string.digits)


class TestRandString:
    def test_length(self):
        assert len(rand_string(17)) == 17

    def test_charset(self):
        assert set(rand_string(500)) <= ALLOWED

    def test_not_constant(self):
        assert rand_string(64) != rand_string(64)

    def test_does_not_come_from_the_seedable_generator(self):
        """R10-2: die Unvorhersagbarkeit war die einzige Token-Eigenschaft ohne Test.

        Länge und Zeichenvorrat sind oben abgedeckt, und ein Tausch von `random.SystemRandom()`
        gegen `random.choice` fiel der ganzen Suite nicht auf -- gemessen per Mutation. Der
        Unterschied ist aber der zwischen einem Geheimnis und einer Rechenaufgabe: der Mersenne
        Twister lässt sich aus wenigen Ausgaben rekonstruieren, und wer als eingeladener Wähler ein
        paar Tokens kennt, könnte die übrigen ausrechnen.

        Geprüft wird die *Wirkung* und nicht die Herkunft: bei gleichem Startwert muss trotzdem
        etwas anderes herauskommen. Das hält auch, wenn jemand `secrets.choice` einsetzt -- und
        fällt, sobald der Zufall aussaatbar wird (ein sehr naheliegender Griff ist `random.seed()`,
        „damit die Tests deterministisch werden").
        """
        random.seed(4711)
        erste = rand_string(64)
        random.seed(4711)
        zweite = rand_string(64)
        assert erste != zweite


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

    def test_without_num_tokens_and_without_choices(self):
        """Seit 3.6 summiert die Datenbank; `Sum()` liefert dann `None` statt `0`."""
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=None)
        assert poll.get_amount_used_unused() == (0, 0, 0)

    def test_counting_is_one_query_per_branch(self, django_assert_num_queries):
        """`.count()`/`aggregate()` statt `len()`: die Zeilen bleiben in der Datenbank."""
        poll = Poll.objects.create(title="P", question_text="?", num_tokens=3)
        for _ in range(3):
            Token.objects.create(poll=poll)
        with django_assert_num_queries(1):
            poll.get_amount_used_unused()

        old = Poll.objects.create(title="Alt", question_text="?", num_tokens=None)
        Choice.objects.create(poll=old, choice_text="A", votes=2)
        with django_assert_num_queries(2):
            old.get_amount_used_unused()


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


@pytest.mark.django_db
class TestPollType:
    """`POLL_TYPES` war eine Liste von Strings, seit 3.6 ist es eine `TextChoices` (Plan 3.6)."""

    def test_values_are_unchanged(self):
        """Die Werte stehen als Spaltenwerte im Bestand -- sie dürfen sich nicht bewegen."""
        assert PollType.values == ["simple_choice", "multiple_choice"]

    def test_default_is_simple_choice(self):
        assert Poll.objects.create(title="P", question_text="?").type == PollType.SIMPLE_CHOICE

    def test_an_unknown_type_is_a_validation_error(self):
        """`choices` bringt die Prüfung ins Modell; vorher gab es sie nur im Formular."""
        poll = Poll(title="P", question_text="?", type="quatsch")
        with pytest.raises(ValidationError):
            poll.full_clean()


@pytest.mark.django_db
class TestGetAbsoluteUrl:
    def test_points_at_the_poll_page(self):
        poll = Poll.objects.create(title="P", question_text="?", identifier="ABC")
        assert poll.get_absolute_url() == "/vote/ABC/"

    def test_matches_the_url_in_the_invitation_mail(self):
        """Die Wähler-Mail baut ihren Link darauf auf (vote/services/mail.py)."""
        poll = Poll.objects.create(title="P", question_text="?")
        assert poll.get_absolute_url() == reverse("vote:polls:poll", args=(poll.identifier,))
