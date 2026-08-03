from smtplib import SMTPException

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from .forms import PollCreateForm
from .models import Choice, Poll, Token


def poll(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    token = request.GET.get("token", "")
    error_message = None
    if token:
        try:
            token_object = Token.objects.get(token_string=token)
        except Token.DoesNotExist:
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
    def create_choice_objects(choices, poll):
        for choice in choices:
            Choice(poll=poll, choice_text=choice).save()

    def create_token_objects(poll, amount):
        result = []
        for _ in range(amount):
            token = Token(poll=poll)
            token.save()
            result.append(token)
        return result

    def send_mail_or_print(args, print_only=False):
        if print_only:
            print(*args)
        else:
            send_mail(*args, fail_silently=False)

    def send_creator_mail(poll, creator_mail, creator_token, print_only=False):
        manage_url = settings.VOTE_BASE_URL + reverse("vote:polls:manage", args=(poll.identifier,))
        args = (
            settings.VOTE_ADMIN_MAIL_SUBJECT % {"title": poll.title},
            settings.VOTE_ADMIN_MAIL_TEXT
            % {"title": poll.title, "manage_url": manage_url, "creator_token": creator_token},
            settings.VOTE_MAIL_FROM,
            [creator_mail],
        )
        send_mail_or_print(args, print_only)

    def send_mails_with_tokens(poll, voter_mails, tokens, print_only=False):
        token_strings = [token.token_string for token in tokens]
        errors = []
        for voter_mail in voter_mails:
            poll_url_with_token = (
                settings.VOTE_BASE_URL
                + reverse("vote:polls:poll", args=(poll.identifier,))
                + "?token="
                + token_strings.pop()
            )
            args = (
                settings.VOTE_MAIL_SUBJECT % {"title": poll.title},
                settings.VOTE_MAIL_TEXT
                % {
                    "title": poll.title,
                    "poll_url_with_token": poll_url_with_token,
                    "vote_base_url": settings.VOTE_BASE_URL,
                },
                settings.VOTE_MAIL_FROM,
                [voter_mail],
            )
            try:
                send_mail_or_print(args, print_only)
            except SMTPException as e:
                errors.append(str(e))
            except UnicodeEncodeError as e:
                errors.append(f"{voter_mail} " + str(e))
        return errors

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
    poll = Poll(
        title=form.cleaned_data["title"],
        type=form.cleaned_data["type"],
        num_tokens=len(voter_mails),
        question_text=form.cleaned_data["description"],
    )
    poll.save()
    create_choice_objects(form.cleaned_data["choices"], poll)
    tokens = create_token_objects(poll, len(voter_mails))
    print_only = not settings.VOTE_SEND_MAILS
    send_creator_mail(poll, form.cleaned_data["creator_mail"], poll.creator_token, print_only)
    errors = send_mails_with_tokens(poll, voter_mails, tokens, print_only)
    return render(request, "vote/create.html", {"errors": errors})


def vote(request, poll_identifier):
    def handle_vote_error(poll, request, message, token_string):
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

    def close_poll_if_all_tokens_redeemed(poll):
        amount_redeemed_tokens, amount_remaining_tokens, amount_redeemed_tokens = (
            poll.get_amount_used_unused()
        )
        if amount_remaining_tokens == 0:
            poll.is_active = False
            poll.save()

    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
    try:
        with transaction.atomic():
            token_string = request.POST["token"]
            token = Token.objects.get(token_string=request.POST["token"])
            if token.poll == poll:
                if poll.type == "multiple_choice":
                    for choice in Choice.objects.filter(poll=poll):
                        if request.POST[f"choice{choice.id}"] == "yes":
                            choice.votes = F("votes") + 1
                            choice.save()
                else:
                    selected_choice = poll.choice_set.get(pk=request.POST["choice"])
                    selected_choice.votes = F("votes") + 1
                    selected_choice.save()
                token.delete()
                close_poll_if_all_tokens_redeemed(poll)
                return HttpResponseRedirect(reverse("vote:polls:success", args=(poll_identifier,)))
            else:
                return handle_vote_error(poll, request, "invalid token.", token_string)

    except KeyError:
        return handle_vote_error(poll, request, "Please fill out all fields.", token_string)
    except Choice.DoesNotExist:
        return handle_vote_error(poll, request, "You didn't select a choice.", token_string)
    except Token.DoesNotExist:
        return handle_vote_error(poll, request, "invalid token.", token_string)


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
