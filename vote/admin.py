"""The admin interface -- deliberately cut back (review R2-1).

It has been registered since 2016, and the user confirmed that a staff account exists in production.
That made `/admin/` the only path in the whole system that could **change vote counts directly** and
**read every voter token** -- one password against the core promise. Both are shut here without
taking the interface away: looking and tidying up still work.

What is deliberately **not** restricted, and why: deleting stays allowed (a poll someone created by
accident or in abuse has to be removable) and `is_active` stays switchable (the creator can do that
with their token too). Django's `LogEntry` records who deleted what.

**The rest is up to the proxy** (notes/to-check.md §B4): `/admin/login/` answers without throttling
failed attempts at all, and that cannot be solved in Django without taking on a dependency.
"""

from django.contrib import admin

from .models import Choice, Poll, Token


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "is_active", "pub_date", "num_tokens")
    list_filter = ("is_active", "type")
    search_fields = ("title", "identifier")
    # `creator_token` is a secret and does not belong on a page that a password opens.
    # `exclude` rather than `readonly_fields`: the latter would still **display** it.
    exclude = ("creator_token",)
    # The identifier is in every invitation mail and every link -- so it is readable anyway, but it
    # must not be changeable: that breaks every link already sent (working rule 5).
    readonly_fields = ("identifier",)


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("choice_text", "poll", "votes")
    list_filter = ("poll",)
    # **The most important bolt:** vote counts are not editable. They are displayed, because a staff
    # account sees them on the results page of a closed poll anyway -- but a number field someone
    # can overwrite is election fraud in a form.
    readonly_fields = ("votes",)


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    """Tokens are visible as a *count*, never as a value.

    Whoever reads a token can vote with it -- anonymity stays intact, but the promise of "one vote
    per invitation" does not. So `token_string` appears neither in the list nor in the form.
    """

    list_display = ("__str__", "poll")
    list_filter = ("poll",)
    fields = ("poll",)
    readonly_fields = ("poll",)
