"""Forms for creating a poll.

`PollCreateForm` validates everything `/vote/create` accepts and has been used by `create()` in
[views.py](views.py) since 3.2.

Why the form exists: `create()` used to read `request.POST` directly and check mail addresses with a
hand-rolled heuristic. Three confirmed bugs came from that and are gone with the form -- a missing
or unknown field ended as a 500 instead of an error message (B3), an invalid address raised an
uncaught `ValidationError` (B12), and addresses entered twice got two tokens, so the same person
could vote twice (B6). On top of that, 3.8 added the cap on the number of recipients (B4).

The field names match the `name` attributes of the existing template; details at the form itself.
See notes/plan.md §7.
"""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import PollType


def parse_lines(text):
    """Splits a textarea field into stripped, non-empty lines, order preserved.

    Replaces `parse_choices`/`parse_mails` from the view. One difference to the old code: it split
    on line breaks in the narrow sense, so a lone carriage return without a line feed (the old Mac
    convention) was not a line boundary. `splitlines()` knows both; for what browsers send the
    result is identical.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


class PollCreateForm(forms.Form):
    """Validates the input from `vote/templates/vote/index.html`.

    The field names match the `name` attributes of the existing form exactly, so that the template
    stays usable unchanged and links to `/vote/create` that have already been sent keep working
    (plan rule 4).

    `cleaned_data` hands back `choices` and `voter_mails` as lists, not as raw text.
    """

    title = forms.CharField(max_length=200)
    type = forms.ChoiceField(choices=PollType.choices)
    # R7-1: lengths capped. `/vote/create` has no authentication, and until here the only effective
    # limit was Django's `DATA_UPLOAD_MAX_MEMORY_SIZE` of 2.5 MB per request -- measured, a 200,000
    # character description and 5,000 choices went through, the latter producing a page of 1.3 MB.
    # The values are generous against any real poll and finite against abuse.
    description = forms.CharField(widget=forms.Textarea, max_length=10_000)
    choices = forms.CharField(widget=forms.Textarea, max_length=20_000)
    creator_mail = forms.EmailField()
    voter_mails = forms.CharField(widget=forms.Textarea)

    def clean_title(self):
        """R5-1: no line breaks -- the title goes into a mail subject.

        Django only strips the outside. A break *inside* makes the message unsendable
        (`BadHeaderError`), and because it sits first in the queue it stops sending for every poll.
        """
        title = self.cleaned_data["title"]
        if "\n" in title or "\r" in title:
            raise ValidationError(
                "The title may not contain line breaks.", code="title_has_line_breaks"
            )
        return title

    def clean_choices(self):
        choices = parse_lines(self.cleaned_data["choices"])
        # The cap on the *count* on top of the text length: 20,000 characters are also 10,000
        # single-character lines, and every choice costs a row on the voting page, a segment in the
        # chart and, for multiple_choice, an UPDATE per vote.
        if len(choices) > settings.VOTE_MAX_CHOICES:
            raise ValidationError(
                "At most %(limit)s choices per poll, got %(count)s.",
                code="too_many_choices",
                params={"limit": settings.VOTE_MAX_CHOICES, "count": len(choices)},
            )
        return choices

    def clean_voter_mails(self):
        # dict rather than set: the input order is preserved, and the key may differ from the
        # address that comes back out (see the deduplication below).
        accepted = {}
        invalid = []
        for mail in parse_lines(self.cleaned_data["voter_mails"]):
            try:
                validate_email(mail)
            except ValidationError:
                invalid.append(mail)
                continue
            # Deduplication against B6. The key is lowercased: mail domains are case-insensitive,
            # and no provider hands out two mailboxes that differ only in case. The first spelling
            # wins, so the mail goes out the way it was entered.
            accepted.setdefault(mail.lower(), mail)
        if invalid:
            # Report every invalid address at once -- whoever pastes a list of 200 addresses does
            # not want 200 attempts. Only what is objectionable is named; the valid addresses from
            # the list do not appear in the message.
            raise ValidationError(
                [
                    ValidationError(
                        "Not a valid mail address: %(mail)s",
                        code="invalid_mail",
                        params={"mail": mail},
                    )
                    for mail in invalid
                ]
            )
        # The cap against B4 (plan 3.8; F5 decided: cap only, no per-IP rate limit). Counted
        # **after** deduplication: what should be limited is the number of mails, and 200 lines with
        # 150 duplicates are 50 mails.
        #
        # The message names both the limit and the actual count, because otherwise the creator would
        # have to guess how far to trim -- and the list is already put back into the field (plan
        # 3.2).
        if len(accepted) > settings.VOTE_MAX_RECIPIENTS:
            raise ValidationError(
                "At most %(limit)s recipients per poll, got %(count)s.",
                code="too_many_recipients",
                params={"limit": settings.VOTE_MAX_RECIPIENTS, "count": len(accepted)},
            )
        return list(accepted.values())
