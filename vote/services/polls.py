"""Creating a poll together with its choices and tokens.

Until 3.5 this was two nested save loops in `create()`: one `INSERT` per choice and one per token.
For 200 recipients that was 200 separate statements -- and, contrary to what was once claimed here,
**not** in one shared transaction: there was no `atomic()`, and Django never read the module-wide
`ATOMIC_REQUESTS` (B16). So every INSERT was its own transaction, taking SQLite's single write slot
and releasing it again -- 200 times (B13). Worse still: if it broke off halfway, half of it stayed.

The service knows neither request nor form, so a management command (goal 2) can call it the same
way.
"""

from django.db import transaction

from ..models import Choice, Poll, Token


@transaction.atomic
def create_poll(*, title, poll_type, question_text, choices, num_tokens):
    """Creates poll, choices and tokens and returns `(poll, tokens)`.

    `transaction.atomic` is **not** redundant -- that was a wrong assumption in 3.5. Django never
    read the module-wide `ATOMIC_REQUESTS` in the settings (reasoning is there), so there is no
    transaction around the request. This decorator is the only thing keeping the function from
    stopping halfway -- inside a request and outside one.

    The tokens come back in the order they were created; the caller pairs them with the recipients.
    """
    poll = Poll.objects.create(
        title=title, type=poll_type, question_text=question_text, num_tokens=num_tokens
    )
    # The order of the choices is the input order and stays that way: bulk_create inserts in list
    # order, and without Meta.ordering SQLite reads them back in rowid order.
    Choice.objects.bulk_create([Choice(poll=poll, choice_text=text) for text in choices])
    # token_string comes from the field default, so it is drawn while constructing the object.
    tokens = Token.objects.bulk_create([Token(poll=poll) for _ in range(num_tokens)])
    return poll, tokens
