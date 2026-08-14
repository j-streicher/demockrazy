import re

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.vary import vary_on_cookie

from .forms import PollCreateForm
from .models import Choice, OutgoingMail, Poll, PollType, Token
from .services import mail, polls

#: The cookie the voter token lives in after the first request (B9). **No `__Host-` prefix**,
#: although that would be the stricter variant: the prefix requires `path=/` and would give up
#: exactly the property that matters here -- one cookie per poll (see `_move_token_out_of_the_url`).
TOKEN_COOKIE_NAME = "vote_token"

#: 30 days. The alternative would be a session cookie that dies with the browser -- stricter, but it
#: would take away something that works today: after the move the history only holds the address
#: *without* the token, so a request from there would arrive without one. The invitation itself sits
#: in the mailbox indefinitely; 30 days are shorter than that.
TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


#: A real token is `[A-Za-z0-9]{128}` (`mk_token()`); the check is more generous only so that a
#: longer token in the future is not silently rejected. For the poll identifier in the same URL,
#: urls.py enforces the same character class with its own converter.
_TOKEN_RE = re.compile(r"\A[A-Za-z0-9]{1,256}\Z")


def _looks_like_a_token(value):
    """R3-1: could the value be a token at all? If not, it does not belong in a cookie.

    Unchecked it was two paths into a 500: a control character makes `http.cookies` raise a
    `CookieError`, and a character beyond Latin-1 produces a header that per PEP 3333 does not
    belong in WSGI.
    """
    return bool(_TOKEN_RE.match(value))


def _token_state(poll):
    """The three numbers `token_state.html` shows -- needed in four places (R14-3)."""
    redeemed, remaining, total = poll.get_amount_used_unused()
    return {
        "amount_redeemed_tokens": redeemed,
        "amount_remaining_tokens": remaining,
        "amount_tokens_total": total,
    }


def _move_token_out_of_the_url(request, poll_identifier):
    """B9: move the token from the query string into a cookie and redirect without it.

    Why at all: `?token=…` appears in the nginx access log, in the browser history and -- because
    the referrer policy sends the *full* URL for same-origin requests (measured: Django sends
    `Referrer-Policy: same-origin`) -- in the `Referer` of every request this page triggers, so in
    every line about a stylesheet too. A token is the only credential there is.

    The move is **additive** (rules 4/5): the link in the mail stays character-identical, old links
    keep working, and the token lives in the URL for exactly *one* request. What it does not make go
    away is the log line of that one request -- that is tied to a clickable link and can only be
    solved at the proxy (`log_format` without `$args`, see notes/to-check.md).

    All four cookie properties have a reason:

    * `path` scoped to this poll. Without it a second invitation would overwrite the first, and with
      `?token=` in the URL that collision did not exist -- so the isolation preserves behaviour, it
      does not add any. The neighbouring paths `…/vote` and `…/results` sit below it, so the cookie
      still reaches the vote itself.
    * `httponly`, because no script needs the token.
    * `samesite="Lax"` and not `"Strict"`: a click from a webmail client is a cross-site navigation,
      and with `Strict` the browser would not send the cookie there -- the redirect would come up
      empty.
    * `secure` from `SESSION_COOKIE_SECURE` rather than from a switch of its own. The production
      module sets exactly that one (via `secureCookies`, default `true`); a second switch would
      silently drift from it. Computing `not DEBUG` at import time would be wrong:
      `demockrazy_config` sets `DEBUG` only *after* the star import, so the value would always be
      `False` there.
    """
    response = HttpResponseRedirect(reverse("vote:polls:poll", args=(poll_identifier,)))
    cookie_path = reverse("vote:polls:poll", args=(poll_identifier,))
    token = request.GET["token"]
    if _looks_like_a_token(token):
        response.set_cookie(
            TOKEN_COOKIE_NAME,
            token,
            max_age=TOKEN_COOKIE_MAX_AGE,
            path=cookie_path,
            secure=settings.SESSION_COOKIE_SECURE,
            httponly=True,
            samesite="Lax",
        )
    else:
        # `?token=` without a value -- or with one that cannot be a token (R3-1) -- means "I have no
        # token" and must not leave an old one in place; otherwise the page shown would contradict
        # the address requested.
        response.delete_cookie(TOKEN_COOKIE_NAME, path=cookie_path)
    return response


# `Vary: Cookie`, because the content of this page now depends on a cookie: a shared cache must not
# hand one voter's page to the next. Measured, the header is already there today -- the CSRF
# middleware sets it, because the form needs a token. But it should be there for the reason it is
# needed, not as a side effect of something else that may change.
# `Cache-Control: no-store` alongside it (R6-2): `Vary: Cookie` tells a cache *what* to distinguish
# by, not that it should not store at all -- and this page shows the token in the form.
@never_cache
@vary_on_cookie
def poll(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        # Moved up: this branch used to sit at the end of the view. It changes nothing about the
        # result, the checks above it have no side effects -- but a token in the URL of a closed
        # poll should not first move into a cookie and then redirect twice.
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
    if "token" in request.GET:
        return _move_token_out_of_the_url(request, poll_identifier)
    # After the move the token comes from the cookie. The form field stays as it was: whoever types
    # their token instead of following the link keeps doing so -- and casting a vote reads it from
    # the POST body, unchanged, not from the cookie.
    token = request.COOKIES.get(TOKEN_COOKIE_NAME, "")
    error_message = None
    # As before, not restricted to this poll: a token of a *different* poll counts as valid here and
    # only shows up when voting. Deliberately left alone -- this is a display question and not a
    # hole (vote() checks the pairing), see notes/plan.md 3.3.
    if token and not Token.objects.filter(token_string=token).exists():
        error_message = "This token is invalid. Maybe you voted already?"
    return render(
        request,
        "vote/poll.html",
        {"poll": poll, "token": token, "error_message": error_message, **_token_state(poll)},
    )


def index(request):
    return render(request, "vote/index.html", {"form": PollCreateForm()})


def create(request):
    if request.method != "POST":
        # A GET on /vote/create used to run into a MultiValueDictKeyError, so into a 500 (B3).
        # Deliberately not a 405: whoever calls the URL from their history or a bookmark should see
        # the form and not end up in a dead end.
        return render(request, "vote/index.html", {"form": PollCreateForm()})

    form = PollCreateForm(request.POST)
    if not form.is_valid():
        # Input errors belong in the form, not on an error page (B3, B12). The bound form carries
        # the input back into the template -- nobody should have to type 200 addresses again.
        return render(request, "vote/index.html", {"form": form})

    voter_mails = form.cleaned_data["voter_mails"]
    # Poll, tokens **and** the mail queue in one transaction. That is the core of the promise from
    # B7, and since the paced sender (plan §11.7) it is kept differently than before: sending
    # happens in another process that only sees committed rows -- so a mail *cannot* go out before
    # its token is durable. Previously the same promise rested on an `on_commit` callback that sent
    # the mails directly.
    #
    # Why enqueueing belongs inside and **not** in an `on_commit`: if it ran afterwards, a crash in
    # between could leave tokens without an invitation. Voters who never learn their token are not
    # just a missing mail -- the poll then never closes by itself, because their tokens are never
    # redeemed.
    with transaction.atomic():
        poll, tokens = polls.create_poll(
            title=form.cleaned_data["title"],
            poll_type=form.cleaned_data["type"],
            question_text=form.cleaned_data["description"],
            choices=form.cleaned_data["choices"],
            num_tokens=len(voter_mails),
        )
        # Render while the objects are here. This is pure template work without I/O; the sender
        # reads the rows later and needs no database access then.
        mail.enqueue(
            mail.poll_created_messages(poll, form.cleaned_data["creator_mail"], voter_mails, tokens)
        )
    return render(request, "vote/create.html")


class _TokenNotConsumed(Exception):
    """This request did not consume the token -- rolls the vote back (R4-1)."""


def vote(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))

    # Read before any try: the error path shows the token in the form again, and this line used to
    # sit *inside* the try -- so a POST without a token field ran into a KeyError whose handler then
    # touched the variable that was never assigned (B2).
    token_string = request.POST.get("token", "")

    def render_error(message):
        return render(
            request,
            "vote/poll.html",
            {
                "poll": poll,
                "error_message": message,
                "token": token_string,
                **_token_state(poll),
            },
        )

    def record_simple_choice():
        """Exactly one vote. Missing field → KeyError, unusable value → ValueError."""
        selected_choice = poll.choice_set.get(pk=request.POST["choice"])
        selected_choice.votes = F("votes") + 1
        selected_choice.save()

    def record_multiple_choice():
        """Every choice has to be answered; a missing field is a KeyError.

        R11-1: one `UPDATE` for all the yes votes instead of one per choice. The loop ran under the
        write lock, which on SQLite affects all four uwsgi processes.
        """
        approved = [
            choice.pk
            for choice in poll.choice_set.all()
            if request.POST[f"choice{choice.id}"] == "yes"
        ]
        if approved:
            Choice.objects.filter(pk__in=approved).update(votes=F("votes") + 1)

    def close_poll_if_all_tokens_redeemed():
        _, amount_remaining_tokens, _ = poll.get_amount_used_unused()
        if amount_remaining_tokens == 0:
            poll.is_active = False
            poll.save()

    try:
        with transaction.atomic():
            # R4-1: **delete first, then record** -- and decide on the deletion. This used to be a
            # `Token.objects.get()` *before* the atomic() block and a `token.delete()` after it; two
            # concurrent requests read the same row, both recorded a vote, and the second `delete()`
            # hit nothing -- which Django accepts silently. Measured: 4 out of 100 double clicks
            # produced two votes from one token.
            # The number of deleted rows is the only answer that reliably says *this* request
            # consumed the token.
            deleted, _ = Token.objects.filter(token_string=token_string, poll=poll).delete()
            if deleted != 1:
                # Four cases, one answer: no token field in the POST, an unknown token, a token of
                # another poll, or a concurrent vote was faster. The first three read "invalid
                # token." before this change as well.
                raise _TokenNotConsumed
            if poll.type == PollType.MULTIPLE_CHOICE:
                record_multiple_choice()
            else:
                record_simple_choice()
            close_poll_if_all_tokens_redeemed()
    except _TokenNotConsumed:
        return render_error("invalid token.")
    except KeyError:
        # An answer field is missing. For multiple_choice the earlier choices of this round have
        # already been incremented, and since R4-1 the token is already deleted -- the atomic()
        # block takes both back, so the token survives.
        return render_error("Please fill out all fields.")
    except (Choice.DoesNotExist, ValueError):
        # No usable choice value. The ValueError comes from the pk lookup when the value is not a
        # number -- that used to be a 500 (B15).
        return render_error("You didn't select a choice.")

    return HttpResponseRedirect(reverse("vote:polls:success", args=(poll_identifier,)))


def success(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    return render(request, "vote/success.html", {"poll": poll})


@never_cache
def manage(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    error_message = None
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
    if request.method == "POST":
        # .get() rather than []: a POST without a token field was a MultiValueDictKeyError, so a 500
        # (B11). An empty token is simply the wrong token -- creator_token is never empty.
        token = request.POST.get("token", "")
        if poll.creator_token == token:
            poll.is_active = False
            poll.save()
            return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
        error_message = "Wrong management token"
    context = {
        "poll": poll,
        "error_message": error_message,
        **_token_state(poll),
        # A bit, not a number: a row carries no poll identifier (F8), so "for this poll" cannot be
        # said. Only the empty direction is safe. Plan §11.7 point 7.
        "mails_pending": OutgoingMail.objects.exists(),
    }
    return render(request, "vote/manage.html", context)


def results(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    token_state = _token_state(poll)
    if poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:poll", args=(poll_identifier,)))
    # Evaluate once and use it for the table *and* the chart: `poll.choice_set.all` in the template
    # queries again on every use.
    choices = list(poll.choice_set.all())
    # The view builds the chart data so the template can emit it via `json_script` instead of
    # interpolating it into a JS string literal (B10). Abstentions only count as a segment for
    # simple_choice -- with multiple_choice nobody chose "nothing", and there the sum of the votes
    # is not the number of voters.
    chart_series = [{"name": choice.choice_text, "y": choice.votes} for choice in choices]
    if poll.type == PollType.SIMPLE_CHOICE:
        chart_series.append({"name": "Abstentions", "y": token_state["amount_remaining_tokens"]})
    return render(
        request,
        "vote/results.html",
        {"poll": poll, "choices": choices, "chart_series": chart_series, **token_state},
    )
