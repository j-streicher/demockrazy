from django.db import transaction
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .forms import PollCreateForm
from .models import Choice, Poll, Token
from .services import mail, polls


def poll(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    token = request.GET.get("token", "")
    error_message = None
    # Wie bisher ohne Einschränkung auf diese Umfrage: ein Token einer *anderen* Umfrage gilt hier
    # als gültig und fällt erst beim Abstimmen auf. Absichtlich nicht mitgeändert -- das ist eine
    # Anzeigefrage und keine Lücke (vote() prüft die Zuordnung), siehe notes/plan.md 3.3.
    if token and not Token.objects.filter(token_string=token).exists():
        error_message = "This token is invalid. Maybe you voted already?"
    amount_redeemed_tokens, amount_remaining_tokens, amount_tokens_total = (
        poll.get_amount_used_unused()
    )
    if poll.is_active:
        return render(
            request,
            "vote/poll.html",
            {
                "poll": poll,
                "token": token,
                "amount_redeemed_tokens": amount_redeemed_tokens,
                "amount_remaining_tokens": amount_remaining_tokens,
                "amount_tokens_total": amount_tokens_total,
                "error_message": error_message,
            },
        )
    else:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))


def index(request):
    return render(request, "vote/index.html", {"form": PollCreateForm()})


def create(request):
    if request.method != "POST":
        # Ein GET auf /vote/create lief bisher in einen MultiValueDictKeyError, also in einen 500
        # (B3). Bewusst kein 405: wer die URL aus der History oder einem Lesezeichen aufruft, soll
        # das Formular sehen und nicht in einer Sackgasse landen.
        return render(request, "vote/index.html", {"form": PollCreateForm()})

    form = PollCreateForm(request.POST)
    if not form.is_valid():
        # Eingabefehler gehören ins Formular, nicht in eine Fehlerseite (B3, B12). Das gebundene
        # Formular trägt die Eingaben zurück in die Vorlage -- niemand soll 200 Adressen erneut
        # eintippen müssen.
        return render(request, "vote/index.html", {"form": form})

    voter_mails = form.cleaned_data["voter_mails"]
    poll, tokens = polls.create_poll(
        title=form.cleaned_data["title"],
        poll_type=form.cleaned_data["type"],
        question_text=form.cleaned_data["description"],
        choices=form.cleaned_data["choices"],
        num_tokens=len(voter_mails),
    )
    # Vollständig rendern, solange die Objekte da sind, aber erst nach dem Commit verschicken (B7):
    # ATOMIC_REQUESTS umschließt den ganzen Request, ein synchrones send_mail() liefe also *in* der
    # Transaktion. Bei einem Rollback wären die Mails mit den Tokens draußen, die Tokens selbst aber
    # nicht in der Datenbank -- Wähler mit einem Link, der nie funktioniert. Umgekehrt hält ein
    # hängender SMTP-Server sonst eine Schreibtransaktion offen, und auf SQLite blockiert das jeden
    # anderen Schreiber (B13).
    messages = mail.poll_created_messages(
        poll, form.cleaned_data["creator_mail"], voter_mails, tokens
    )
    transaction.on_commit(lambda: mail.deliver(messages))
    return render(request, "vote/create.html")


def vote(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))

    # Vor jedem try lesen: der Fehlerpfad zeigt den Token wieder im Formular an, und bisher stand
    # diese Zeile *innerhalb* des try -- ein POST ohne Token-Feld lief damit in einen KeyError,
    # dessen Handler auf die nie zugewiesene Variable zugriff (B2).
    token_string = request.POST.get("token", "")

    def render_error(message):
        amount_redeemed_tokens, amount_remaining_tokens, amount_tokens_total = (
            poll.get_amount_used_unused()
        )
        return render(
            request,
            "vote/poll.html",
            {
                "poll": poll,
                "error_message": message,
                "token": token_string,
                "amount_redeemed_tokens": amount_redeemed_tokens,
                "amount_remaining_tokens": amount_remaining_tokens,
                "amount_tokens_total": amount_tokens_total,
            },
        )

    def record_simple_choice():
        """Genau eine Stimme. Fehlendes Feld → KeyError, unbrauchbarer Wert → ValueError."""
        selected_choice = poll.choice_set.get(pk=request.POST["choice"])
        selected_choice.votes = F("votes") + 1
        selected_choice.save()

    def record_multiple_choice():
        """Jede Choice muss beantwortet sein; ein fehlendes Feld ist ein KeyError."""
        for choice in poll.choice_set.all():
            if request.POST[f"choice{choice.id}"] == "yes":
                choice.votes = F("votes") + 1
                choice.save()

    def close_poll_if_all_tokens_redeemed():
        _, amount_remaining_tokens, _ = poll.get_amount_used_unused()
        if amount_remaining_tokens == 0:
            poll.is_active = False
            poll.save()

    try:
        token = Token.objects.get(token_string=token_string, poll=poll)
    except Token.DoesNotExist:
        # Drei Fälle, eine Antwort: kein Token-Feld im POST, ein unbekannter Token, oder ein Token,
        # der zu einer anderen Umfrage gehört. Alle drei hießen auch bisher "invalid token."
        return render_error("invalid token.")

    try:
        with transaction.atomic():
            if poll.type == "multiple_choice":
                record_multiple_choice()
            else:
                record_simple_choice()
            token.delete()
            close_poll_if_all_tokens_redeemed()
    except KeyError:
        # Ein Antwortfeld fehlt. Bei multiple_choice sind die vorherigen Choices dieser Runde schon
        # hochgezählt -- der atomic()-Block nimmt sie zurück, der Token bleibt erhalten.
        return render_error("Please fill out all fields.")
    except (Choice.DoesNotExist, ValueError):
        # Kein brauchbarer choice-Wert. Der ValueError kommt aus dem pk-Lookup, wenn der Wert keine
        # Zahl ist -- das war bisher ein 500 (B15).
        return render_error("You didn't select a choice.")

    return HttpResponseRedirect(reverse("vote:polls:success", args=(poll_identifier,)))


def success(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    return render(request, "vote/success.html", {"poll": poll})


def manage(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    error_message = None
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
    if request.method == "POST":
        # .get() statt []: ein POST ohne Token-Feld war ein MultiValueDictKeyError, also ein 500
        # (B11). Ein leerer Token ist einfach der falsche Token -- creator_token ist nie leer.
        token = request.POST.get("token", "")
        if poll.creator_token == token:
            poll.is_active = False
            poll.save()
            return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
        error_message = "Wrong management token"
    amount_redeemed_tokens, amount_remaining_tokens, amount_tokens_total = (
        poll.get_amount_used_unused()
    )
    context = {
        "poll": poll,
        "amount_redeemed_tokens": amount_redeemed_tokens,
        "amount_remaining_tokens": amount_remaining_tokens,
        "amount_tokens_total": amount_tokens_total,
        "error_message": error_message,
    }
    return render(request, "vote/manage.html", context)


def results(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    amount_redeemed_tokens, amount_remaining_tokens, amount_tokens_total = (
        poll.get_amount_used_unused()
    )
    if poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:poll", args=(poll_identifier,)))
    return render(
        request,
        "vote/results.html",
        {
            "poll": poll,
            "amount_redeemed_tokens": amount_redeemed_tokens,
            "amount_remaining_tokens": amount_remaining_tokens,
            "amount_tokens_total": amount_tokens_total,
        },
    )
