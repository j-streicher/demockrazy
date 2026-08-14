import random
import string

from django.db import models
from django.urls import reverse
from django.utils.timezone import now


class PollType(models.TextChoices):
    """The two kinds of poll. Values unchanged, they are column values in the existing data."""

    SIMPLE_CHOICE = "simple_choice", "Simple Choice"
    MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"


def rand_string(length):
    return "".join(
        random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(length)
    )


# Until 3.6 the three generators checked after drawing whether the value already existed and called
# themselves again on a collision. That cost one query per token -- 200 queries for 200 recipients,
# and it was the only part of creating a poll that still grew linearly (plan 3.5). The check is gone
# because it was the wrong one: it could not see the siblings of a bulk_create batch and could not
# guarantee uniqueness anyway. The database enforces it now (UniqueConstraint below). With 62^64 and
# 62^128 possible values a collision is not an operational case but a reason to doubt the RNG.
def mk_admin_token():
    return rand_string(256)


def mk_identifier():
    return rand_string(64)


def mk_token():
    return rand_string(128)


class Poll(models.Model):
    title = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=PollType.choices, default=PollType.SIMPLE_CHOICE)
    num_tokens = models.IntegerField(blank=True, null=True)
    question_text = models.TextField()
    pub_date = models.DateTimeField("date published", default=now, blank=True)
    creator_token = models.CharField(max_length=512, default=mk_admin_token)
    identifier = models.CharField(max_length=64, default=mk_identifier)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            # `identifier` is the lookup key in every request and was always treated as unique --
            # nothing enforced it. On SQLite the constraint implicitly creates
            # `sqlite_autoindex_vote_poll_1`, so it covers those lookups too; an additional
            # `db_index` would be a second index on the same column.
            #
            # Careful, measured against a copy of the production schema: SQLite cannot add a
            # constraint after the fact, so Django **rebuilds the table** (CREATE/INSERT/DROP/
            # RENAME). For `vote_poll` that changes nothing else, for `vote_token` it also
            # normalises the 2016 definitions -- details in notes/phase-2-migrations.md.
            models.UniqueConstraint(fields=["identifier"], name="vote_poll_identifier_unique"),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("vote:polls:poll", args=(self.identifier,))

    def get_amount_used_unused(self):
        amount_remaining_tokens = self.token_set.count()
        if self.num_tokens is not None:
            total = self.num_tokens
            amount_redeemed_tokens = total - amount_remaining_tokens
        else:
            # Old polls without a recipient list: what was cast is only in the choices.
            # Sum() returns None when there are none.
            amount_redeemed_tokens = (
                self.choice_set.aggregate(models.Sum("votes"))["votes__sum"] or 0
            )
            total = amount_redeemed_tokens + amount_remaining_tokens
        return (amount_redeemed_tokens, amount_remaining_tokens, total)


class Choice(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE)
    choice_text = models.TextField()
    votes = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.poll} - {self.choice_text}"


class Token(models.Model):
    poll = models.ForeignKey(Poll, on_delete=models.CASCADE)
    token_string = models.CharField(default=mk_token, max_length=128)

    class Meta:
        constraints = [
            # The token is the only credential a vote has -- uniqueness belongs in the database, not
            # in a check beforehand that cannot guarantee it.
            # The table rebuild (see Poll.Meta) additionally makes the foreign key here
            # `DEFERRABLE INITIALLY DEFERRED` and renames `vote_token_582e9e5a` to
            # `vote_token_poll_id_e1049aa3`. Both are what a fresh `migrate` produces anyway; it
            # removes exactly the divergence notes/phase-2-migrations.md recorded as a future risk.
            models.UniqueConstraint(fields=["token_string"], name="vote_token_token_string_unique"),
        ]

    def __str__(self):
        return f"{self.poll} Token"


class OutgoingMail(models.Model):
    """A mail that has not gone out yet. The queue of the paced sender (plan §11.7).

    **Why this table exists:** the mail server throttles by messages per time window, so sending has
    to be spread over minutes, and that cannot happen inside a request. The pairing "which text goes
    to which address" therefore needs somewhere that survives a restart -- otherwise a restart in
    the middle of a run loses the remaining invitations without anyone being able to say which.

    **What deliberately is *not* here, and this is the important part (F8, plan §11.4):**

    * **No poll identifier as a column** -- no foreign key, nothing to group rows by. **The rendered
      text contains the voting link and with it the `identifier`**, and `recipient` sits next to it:
      as long as the row exists it says "this address is invited to this poll and holds this token".
      That is the loss weighed under F8 (plan §11.4) and the reason a delivered row is *deleted* --
      this said "a row does not say on its own which poll it belongs to", which is true of the
      columns and not of the row (review R1-1).
    * **No timestamp.** It would be a fingerprint: same second = same poll. It is not needed either,
      the order is in the id and giving up is in `attempts`.
    * **No `sent` flag and no history.** A delivered row is **deleted**. After a run the state is
      exactly what it was before.

    So while a run is in progress, *who was invited* is exposed -- **not how anyone voted.** The
    token is deleted when the vote is cast and the vote carries no identifier; the core promise is
    untouched.
    """

    recipient = models.EmailField()
    # TextField rather than CharField: the subject length follows from the poll title (up to 200
    # characters) plus a prefix, so an upper bound would be a trap that SQLite does not even enforce
    # -- `bulk_create` does not validate. Nothing here is sorted or indexed.
    subject = models.TextField()
    body = models.TextField()
    # Counts **only** rejections by the server for this very message, not connection trouble.
    # Why the difference matters is in vote/services/mail.py at `send_pending()`.
    attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        # No address: the same restraint as the log call in `send_pending()` (F8).
        return f"Ausgehende Mail #{self.pk}"
