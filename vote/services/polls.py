"""Anlegen einer Umfrage samt Choices und Tokens.

Bis 3.5 stand das als zwei geschachtelte Save-Schleifen in `create()`: ein `INSERT` pro Choice und
ein `INSERT` pro Token. Bei 200 Empfängern waren das 200 einzelne Statements -- und, anders als hier
mal behauptet, **nicht** in einer gemeinsamen Transaktion: ein `atomic()` gab es nicht, und das
modulweite `ATOMIC_REQUESTS` hat Django nie gelesen (B16). Jedes INSERT war also seine eigene
Transaktion, die den einzigen Schreib-Slot von SQLite nahm und wieder freigab -- 200 Mal (B13).
Schlimmer noch: brach es auf halbem Weg ab, blieb die Hälfte stehen.

Der Service kennt weder Request noch Formular, damit ein Management-Command (Ziel 2) ihn genauso
aufrufen kann.
"""

from django.db import transaction

from ..models import Choice, Poll, Token


@transaction.atomic
def create_poll(*, title, poll_type, question_text, choices, num_tokens):
    """Legt Umfrage, Choices und Tokens an und liefert `(poll, tokens)`.

    `transaction.atomic` ist **nicht** redundant -- das war eine falsche Annahme aus 3.5. Das
    modulweite `ATOMIC_REQUESTS` in den Settings hat Django nie gelesen (Begründung dort), es gibt
    also keine Transaktion um den Request. Dieser Dekorator ist das Einzige, was verhindert, dass
    die Funktion auf halbem Weg stehenbleibt -- im Request wie außerhalb.

    Die Tokens kommen in derselben Reihenfolge zurück, in der sie erzeugt wurden; der Aufrufer
    ordnet sie den Empfängern zu.
    """
    poll = Poll.objects.create(
        title=title, type=poll_type, question_text=question_text, num_tokens=num_tokens
    )
    # Reihenfolge der Choices ist die Eingabereihenfolge und bleibt es: bulk_create fügt in
    # Listenreihenfolge ein, und ohne Meta.ordering liest SQLite in rowid-Reihenfolge zurück.
    Choice.objects.bulk_create([Choice(poll=poll, choice_text=text) for text in choices])
    # token_string kommt aus dem Feld-Default, wird also schon beim Konstruieren gezogen.
    tokens = Token.objects.bulk_create([Token(poll=poll) for _ in range(num_tokens)])
    return poll, tokens
