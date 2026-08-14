"""Tests for vote/forms.py.

The form appeared in 3.1, `create()` has used it since 3.2, and since 3.8 it carries the cap on the
number of recipients (B4). These tests check it directly; that the *view* behaves accordingly is in
test_views.py and test_known_bugs.py.

They were originally written as the only assurance that the form behaves like the view helpers it
replaces (B3, B6, B12). What those helpers actually did is recorded in notes/phase-0-baseline.md.
"""

import pytest

from vote.forms import PollCreateForm, parse_lines


def payload(**overrides):
    data = {
        "title": "Testabstimmung",
        "type": "simple_choice",
        "description": "Wollen wir das?",
        "choices": "Ja\nNein",
        "creator_mail": "admin@example.org",
        "voter_mails": "erste@example.org\nzweite@example.org",
    }
    data.update(overrides)
    return data


class TestParseLines:
    def test_trims_and_drops_blank_lines(self):
        assert parse_lines("Ja\nNein\n\n  Vielleicht  \n") == ["Ja", "Nein", "Vielleicht"]

    def test_keeps_order(self):
        assert parse_lines("C\nA\nB") == ["C", "A", "B"]

    def test_handles_crlf(self):
        assert parse_lines("Ja\r\nNein\r\n") == ["Ja", "Nein"]

    def test_empty_input(self):
        assert parse_lines("   \n\n  ") == []


class TestValidPayload:
    def test_is_valid(self):
        assert PollCreateForm(payload()).is_valid()

    def test_parses_choices_into_a_list(self):
        form = PollCreateForm(payload(choices="Ja\nNein\n\n  Vielleicht  \n"))
        assert form.is_valid()
        assert form.cleaned_data["choices"] == ["Ja", "Nein", "Vielleicht"]

    def test_parses_voter_mails_into_a_list(self):
        form = PollCreateForm(payload(voter_mails="a@example.org\n\n  b@example.org  \n"))
        assert form.is_valid()
        assert form.cleaned_data["voter_mails"] == ["a@example.org", "b@example.org"]

    def test_title_is_trimmed(self):
        form = PollCreateForm(payload(title="  Testabstimmung  "))
        assert form.is_valid()
        assert form.cleaned_data["title"] == "Testabstimmung"

    @pytest.mark.parametrize("poll_type", ["simple_choice", "multiple_choice"])
    def test_accepts_both_poll_types(self, poll_type):
        form = PollCreateForm(payload(type=poll_type))
        assert form.is_valid()
        assert form.cleaned_data["type"] == poll_type


class TestDeduplication:
    """B6: the same address entered twice produced several tokens and with them several votes."""

    def test_exact_duplicates_collapse(self):
        form = PollCreateForm(payload(voter_mails="dup@example.org\n" * 3))
        assert form.is_valid()
        assert form.cleaned_data["voter_mails"] == ["dup@example.org"]

    def test_duplicates_differing_only_in_case_collapse(self):
        form = PollCreateForm(payload(voter_mails="Max@example.org\nmax@EXAMPLE.org"))
        assert form.is_valid()
        assert form.cleaned_data["voter_mails"] == ["Max@example.org"]

    def test_first_spelling_wins(self):
        """The mail should go out the way it was entered."""
        form = PollCreateForm(payload(voter_mails="MAX@example.org\nmax@example.org"))
        assert form.is_valid()
        assert form.cleaned_data["voter_mails"] == ["MAX@example.org"]

    def test_distinct_addresses_survive(self):
        form = PollCreateForm(payload(voter_mails="a@example.org\nb@example.org\na@example.org"))
        assert form.is_valid()
        assert form.cleaned_data["voter_mails"] == ["a@example.org", "b@example.org"]


class TestInvalidMailAddresses:
    """B12: a broken address ended in an uncaught ValidationError, so in a 500."""

    @pytest.mark.parametrize(
        "address",
        [
            "KAPUTT",
            "kein@punkt",
            "zwei@@example.org",
            "mit leerzeichen@example.org",
            "@example.org",
        ],
    )
    def test_rejects(self, address):
        form = PollCreateForm(payload(voter_mails=f"gueltig@example.org\n{address}"))
        assert not form.is_valid()
        assert "voter_mails" in form.errors

    def test_error_names_the_offending_address(self):
        form = PollCreateForm(payload(voter_mails="gueltig@example.org\nKAPUTT"))
        assert not form.is_valid()
        assert "KAPUTT" in " ".join(form.errors["voter_mails"])

    def test_error_does_not_repeat_the_valid_addresses(self):
        form = PollCreateForm(payload(voter_mails="gueltig@example.org\nKAPUTT"))
        assert not form.is_valid()
        assert "gueltig@example.org" not in " ".join(form.errors["voter_mails"])

    def test_reports_all_offending_addresses_at_once(self):
        form = PollCreateForm(payload(voter_mails="EINS\ngueltig@example.org\nZWEI"))
        assert not form.is_valid()
        messages = " ".join(form.errors["voter_mails"])
        assert "EINS" in messages
        assert "ZWEI" in messages

    def test_an_invalid_creator_mail_is_a_field_error(self):
        form = PollCreateForm(payload(creator_mail="KAPUTT"))
        assert not form.is_valid()
        assert "creator_mail" in form.errors


class TestRejectedInput:
    """Input the view used to turn silently into unusable polls."""

    def test_unknown_poll_type_is_a_field_error(self):
        """B3: `raise Exception('Invalid poll type')` was a 500."""
        form = PollCreateForm(payload(type="quatsch"))
        assert not form.is_valid()
        assert "type" in form.errors

    @pytest.mark.parametrize(
        "field", ["title", "type", "description", "choices", "creator_mail", "voter_mails"]
    )
    def test_every_field_is_required(self, field):
        form = PollCreateForm(payload(**{field: ""}))
        assert not form.is_valid()
        assert field in form.errors

    @pytest.mark.parametrize("field", ["choices", "voter_mails"])
    def test_whitespace_only_is_not_input(self, field):
        form = PollCreateForm(payload(**{field: "  \n\n  "}))
        assert not form.is_valid()
        assert field in form.errors

    def test_missing_field_is_an_error_not_an_exception(self):
        """B3: `request.POST['title']` raised a MultiValueDictKeyError."""
        data = payload()
        del data["title"]
        form = PollCreateForm(data)
        assert not form.is_valid()
        assert "title" in form.errors

    def test_title_longer_than_the_column_is_rejected(self):
        """The model field is `varchar(200)`; SQLite would accept more without a word."""
        form = PollCreateForm(payload(title="x" * 201))
        assert not form.is_valid()
        assert "title" in form.errors

    def test_title_at_the_column_limit_is_accepted(self):
        assert PollCreateForm(payload(title="x" * 200)).is_valid()

    @pytest.mark.parametrize("line_break", ["\n", "\r", "\r\n"])
    def test_title_with_a_line_break_is_rejected(self, line_break):
        """R5-1: the title goes into a mail subject, and a break there is not deliverable.

        Django only strips the outside, so a break in the middle got through -- and made the first
        row of the queue unsendable, which stopped sending for *every* poll.
        """
        form = PollCreateForm(payload(title=f"Kaffee{line_break}Bcc: leak@example.org"))
        assert not form.is_valid()
        assert "title" in form.errors


class TestSizeCaps:
    """R7-1: apart from the number of recipients, nothing was capped.

    Measured, an unauthenticated POST got 200,000 characters of description and 5,000 choices
    through; the latter produced a voting page of 1.3 MB. The only effective limit was Django's
    `DATA_UPLOAD_MAX_MEMORY_SIZE` of 2.5 MB per request, and that was nowhere written down as a
    decision.
    """

    def test_a_very_long_description_is_rejected(self):
        form = PollCreateForm(payload(description="x" * 10_001))
        assert not form.is_valid()
        assert "description" in form.errors

    def test_a_description_at_the_limit_is_accepted(self):
        assert PollCreateForm(payload(description="x" * 10_000)).is_valid()

    def test_a_very_long_choices_field_is_rejected(self):
        form = PollCreateForm(payload(choices="a\n" * 10_001))
        assert not form.is_valid()
        assert "choices" in form.errors

    def test_too_many_choices_are_rejected(self, settings):
        """The count on top of the length: 20,000 characters are also 10,000 one-character lines."""
        settings.VOTE_MAX_CHOICES = 3
        form = PollCreateForm(payload(choices="a\nb\nc\nd"))
        assert not form.is_valid()
        assert form.errors["choices"] == ["At most 3 choices per poll, got 4."]

    def test_exactly_at_the_choice_limit_is_accepted(self, settings):
        settings.VOTE_MAX_CHOICES = 3
        form = PollCreateForm(payload(choices="a\nb\nc"))
        assert form.is_valid(), form.errors
        assert form.cleaned_data["choices"] == ["a", "b", "c"]

    def test_blank_lines_do_not_count_towards_the_limit(self, settings):
        """What is counted is what becomes a choice -- `parse_lines` drops blank lines first."""
        settings.VOTE_MAX_CHOICES = 3
        assert PollCreateForm(payload(choices="a\n\n\nb\n\nc\n")).is_valid()


class TestRecipientCap:
    """The cap against B4 (plan 3.8). The limit lives in settings.VOTE_MAX_RECIPIENTS."""

    @staticmethod
    def _mails(count):
        return "\n".join(f"w{i}@example.org" for i in range(count))

    def test_exactly_at_the_limit_is_accepted(self, settings):
        settings.VOTE_MAX_RECIPIENTS = 3
        form = PollCreateForm(data=payload(voter_mails=self._mails(3)))
        assert form.is_valid(), form.errors
        assert len(form.cleaned_data["voter_mails"]) == 3

    def test_one_over_the_limit_is_rejected(self, settings):
        settings.VOTE_MAX_RECIPIENTS = 3
        form = PollCreateForm(data=payload(voter_mails=self._mails(4)))
        assert not form.is_valid()
        assert form.errors["voter_mails"] == ["At most 3 recipients per poll, got 4."]

    def test_duplicates_are_counted_after_dedup(self, settings):
        """What should be limited is the number of mails -- and duplicates cost none.

        Without this order a list with many repetitions would be rejected even though only a few
        mails come out of it.
        """
        settings.VOTE_MAX_RECIPIENTS = 3
        form = PollCreateForm(data=payload(voter_mails="a@example.org\n" * 10))
        assert form.is_valid(), form.errors
        assert form.cleaned_data["voter_mails"] == ["a@example.org"]

    def test_the_default_is_above_the_real_world_maximum(self):
        """60--100 recipients occur in practice (F13). A cap below that would be an outage.

        Not for its own sake: the number was chosen by the user, and this test records why it must
        not be smaller.
        """
        from django.conf import settings as django_settings

        assert django_settings.VOTE_MAX_RECIPIENTS >= 100
