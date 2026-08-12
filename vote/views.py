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

#: Cookie, in dem der Wähler-Token nach dem ersten Aufruf liegt (B9).
#: **Kein `__Host-`-Präfix**, obwohl das die härtere Variante wäre: das Präfix verlangt `path=/`
#: und würde damit genau die Eigenschaft aufgeben, auf die es hier ankommt -- ein Cookie pro
#: Umfrage (siehe `_move_token_out_of_the_url`).
TOKEN_COOKIE_NAME = "vote_token"

#: 30 Tage. Die Alternative wäre ein Sitzungscookie, das mit dem Browser stirbt -- das wäre
#: strenger, würde aber etwas wegnehmen, was heute funktioniert: nach dem Umzug steht in der
#: History nur noch die Adresse *ohne* Token, ein Aufruf von dort käme also ohne Token an. Die
#: Einladung selbst liegt zeitlich unbegrenzt in der Mailbox; 30 Tage sind kürzer als das.
TOKEN_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


#: Ein echter Token ist `[A-Za-z0-9]{128}` (`mk_token()`); großzügiger geprüft wird nur, damit ein
#: künftig längerer Token nicht still abgewiesen wird. Für die Umfragekennung in derselben URL
#: erzwingt urls.py dieselbe Zeichenklasse mit einem eigenen Converter.
_TOKEN_RE = re.compile(r"\A[A-Za-z0-9]{1,256}\Z")


def _looks_like_a_token(value):
    """R3-1: taugt der Wert überhaupt als Token? Sonst gehört er nicht in ein Cookie.

    Ungeprüft war er zwei Wege in einen 500: ein Steuerzeichen wirft in `http.cookies` einen
    `CookieError`, ein Zeichen jenseits von Latin-1 erzeugt einen Header, der nach PEP 3333 nicht in
    WSGI gehört.
    """
    return bool(_TOKEN_RE.match(value))


def _token_state(poll):
    """Die drei Zahlen, die `token_state.html` anzeigt -- an vier Stellen gebraucht (R14-3)."""
    redeemed, remaining, total = poll.get_amount_used_unused()
    return {
        "amount_redeemed_tokens": redeemed,
        "amount_remaining_tokens": remaining,
        "amount_tokens_total": total,
    }


def _move_token_out_of_the_url(request, poll_identifier):
    """B9: den Token aus dem Query-String in ein Cookie umziehen und ohne ihn umleiten.

    Warum überhaupt: `?token=…` steht im nginx-Access-Log, in der Browser-History und -- weil die
    Referrer-Policy für gleichherkünftige Anfragen die *vollständige* URL sendet (gemessen: Django
    schickt `Referrer-Policy: same-origin`) -- im `Referer` jeder Anfrage, die diese Seite auslöst,
    also auch in jeder Zeile über ein Stylesheet. Ein Token ist das einzige Auth-Merkmal.

    Der Umzug ist **additiv** (Regel 4/5): der Link in der Mail bleibt zeichengleich, alte Links
    funktionieren weiter, der Token lebt in der URL nur noch für *einen* Request. Was dadurch
    nicht verschwindet, ist die Logzeile dieses einen Aufrufs -- die ist an einen klickbaren Link
    gebunden und nur am Proxy zu lösen (`log_format` ohne `$args`, siehe notes/to-check.md).

    Die Cookie-Eigenschaften sind alle vier begründet:

    * `path` auf den Pfad dieser Umfrage. Ohne das würde eine zweite Einladung die erste
      überschreiben, und mit `?token=` in der URL gab es diese Kollision nicht -- die Isolation
      ist also Verhaltenserhaltung, keine Zugabe. Die Nachbarpfade `…/vote` und `…/results`
      liegen darunter, das Cookie erreicht die Stimmabgabe damit weiterhin.
    * `httponly`, weil kein Skript den Token braucht.
    * `samesite="Lax"` und nicht `"Strict"`: der Klick aus einem Webmailer ist eine
      seitenübergreifende Navigation, und bei `Strict` schickt der Browser das Cookie dort nicht
      mit -- die Weiterleitung liefe ins Leere.
    * `secure` aus `SESSION_COOKIE_SECURE` statt aus einem eigenen Schalter. Das Prod-Modul setzt
      genau diesen (über `secureCookies`, Default `true`), ein zweiter Schalter würde still davon
      abweichen. Zur Importzeit `not DEBUG` zu rechnen wäre falsch: `demockrazy_config` setzt
      `DEBUG` erst *nach* dem Sternchen-Import, der Wert wäre dort immer `False`.
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
        # `?token=` ohne Wert -- oder mit einem Wert, der keiner sein kann (R3-1) -- heißt "ich habe
        # keinen Token" und soll einen alten nicht stehen lassen; sonst widerspräche die angezeigte
        # Seite der aufgerufenen Adresse.
        response.delete_cookie(TOKEN_COOKIE_NAME, path=cookie_path)
    return response


# `Vary: Cookie`, weil der Inhalt dieser Seite jetzt von einem Cookie abhängt: ein gemeinsamer
# Cache darf die Seite eines Wählers nicht an den nächsten ausliefern. Gemessen ist der Header
# heute schon da -- die CSRF-Middleware setzt ihn, weil das Formular ein Token braucht. Er soll
# aber aus dem Grund dastehen, aus dem er gebraucht wird, und nicht als Nebenwirkung von etwas
# anderem, das sich ändern kann.
# `Cache-Control: no-store` dazu (R6-2): `Vary: Cookie` sagt einem Cache, *wonach* er unterscheiden
# muss, aber nicht, dass er nicht speichern soll -- und diese Seite zeigt den Token im Formular.
@never_cache
@vary_on_cookie
def poll(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        # Vorgezogen: diese Weiche stand bisher am Ende der View. Am Ergebnis ändert das nichts,
        # die Prüfungen darüber haben keine Nebenwirkungen -- aber ein Token in der URL einer
        # geschlossenen Umfrage soll nicht erst umziehen und dann zweimal weiterleiten.
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))
    if "token" in request.GET:
        return _move_token_out_of_the_url(request, poll_identifier)
    # Nach dem Umzug kommt der Token aus dem Cookie. Das Formularfeld bleibt, wie es war: wer
    # seinen Token abtippt, statt dem Link zu folgen, tut das weiter -- und die Stimmabgabe liest
    # ihn unverändert aus dem POST-Body, nicht aus dem Cookie.
    token = request.COOKIES.get(TOKEN_COOKIE_NAME, "")
    error_message = None
    # Wie bisher ohne Einschränkung auf diese Umfrage: ein Token einer *anderen* Umfrage gilt hier
    # als gültig und fällt erst beim Abstimmen auf. Absichtlich nicht mitgeändert -- das ist eine
    # Anzeigefrage und keine Lücke (vote() prüft die Zuordnung), siehe notes/plan.md 3.3.
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
    # Umfrage, Tokens **und** die Mail-Warteschlange in einer Transaktion. Das ist der Kern der
    # Zusage aus B7, und seit dem getakteten Versand (Plan §11.7) erfüllt sie sich anders als
    # vorher: verschickt wird in einem anderen Prozess, der nur committete Zeilen sieht -- eine Mail
    # *kann* also nicht rausgehen, bevor ihr Token durabel ist. Vorher hing dieselbe Zusage an einem
    # `on_commit`-Callback, der die Mails direkt verschickte.
    #
    # Warum das Einreihen mit hineingehört und **nicht** in ein `on_commit`: liefe es danach, könnte
    # ein Absturz dazwischen Tokens ohne Einladung hinterlassen. Wähler, die ihren Token nie
    # erfahren, sind nicht nur eine fehlende Mail -- die Umfrage schließt dann nie von selbst, weil
    # ihre Tokens nie verbraucht werden.
    with transaction.atomic():
        poll, tokens = polls.create_poll(
            title=form.cleaned_data["title"],
            poll_type=form.cleaned_data["type"],
            question_text=form.cleaned_data["description"],
            choices=form.cleaned_data["choices"],
            num_tokens=len(voter_mails),
        )
        # Rendern, solange die Objekte da sind. Das ist reine Template-Arbeit ohne I/O; der Versand
        # liest die Zeilen später und braucht dann keinen Datenbankzugriff mehr.
        mail.enqueue(
            mail.poll_created_messages(poll, form.cleaned_data["creator_mail"], voter_mails, tokens)
        )
    return render(request, "vote/create.html")


class _TokenNotConsumed(Exception):
    """Diese Anfrage hat den Token nicht verbraucht -- rollt die Stimme zurück (R4-1)."""


def vote(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    if not poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:result", args=(poll_identifier,)))

    # Vor jedem try lesen: der Fehlerpfad zeigt den Token wieder im Formular an, und bisher stand
    # diese Zeile *innerhalb* des try -- ein POST ohne Token-Feld lief damit in einen KeyError,
    # dessen Handler auf die nie zugewiesene Variable zugriff (B2).
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
        """Genau eine Stimme. Fehlendes Feld → KeyError, unbrauchbarer Wert → ValueError."""
        selected_choice = poll.choice_set.get(pk=request.POST["choice"])
        selected_choice.votes = F("votes") + 1
        selected_choice.save()

    def record_multiple_choice():
        """Jede Choice muss beantwortet sein; ein fehlendes Feld ist ein KeyError.

        R11-1: ein `UPDATE` für alle Ja-Stimmen statt eines pro Choice. Die Schleife lief unter der
        Schreibsperre, die auf SQLite alle vier uwsgi-Prozesse betrifft.
        """
        angenommen = [
            choice.pk
            for choice in poll.choice_set.all()
            if request.POST[f"choice{choice.id}"] == "yes"
        ]
        if angenommen:
            Choice.objects.filter(pk__in=angenommen).update(votes=F("votes") + 1)

    def close_poll_if_all_tokens_redeemed():
        _, amount_remaining_tokens, _ = poll.get_amount_used_unused()
        if amount_remaining_tokens == 0:
            poll.is_active = False
            poll.save()

    try:
        with transaction.atomic():
            # R4-1: **erst löschen, dann buchen** -- und an der Löschung entscheiden. Vorher stand
            # hier ein `Token.objects.get()` *vor* dem atomic()-Block und ein `token.delete()`
            # dahinter; zwei gleichzeitige Anfragen lasen damit dieselbe Zeile, buchten beide eine
            # Stimme, und das zweite `delete()` traf ins Leere -- was Django stillschweigend
            # hinnimmt. Gemessen: 4 von 100 Doppelklicks ergaben zwei Stimmen aus einem Token.
            # Die gelöschte Zeilenzahl ist die einzige Auskunft, die verlässlich sagt, dass *diese*
            # Anfrage den Token verbraucht hat.
            deleted, _ = Token.objects.filter(token_string=token_string, poll=poll).delete()
            if deleted != 1:
                # Vier Fälle, eine Antwort: kein Token-Feld im POST, ein unbekannter Token, ein
                # Token einer anderen Umfrage, oder eine gleichzeitige Abgabe war schneller. Die
                # ersten drei hießen auch bisher "invalid token."
                raise _TokenNotConsumed
            if poll.type == PollType.MULTIPLE_CHOICE:
                record_multiple_choice()
            else:
                record_simple_choice()
            close_poll_if_all_tokens_redeemed()
    except _TokenNotConsumed:
        return render_error("invalid token.")
    except KeyError:
        # Ein Antwortfeld fehlt. Bei multiple_choice sind die vorherigen Choices dieser Runde schon
        # hochgezählt, und seit R4-1 ist der Token schon gelöscht -- der atomic()-Block nimmt beides
        # zurück, der Token bleibt also erhalten.
        return render_error("Please fill out all fields.")
    except (Choice.DoesNotExist, ValueError):
        # Kein brauchbarer choice-Wert. Der ValueError kommt aus dem pk-Lookup, wenn der Wert keine
        # Zahl ist -- das war bisher ein 500 (B15).
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
        # .get() statt []: ein POST ohne Token-Feld war ein MultiValueDictKeyError, also ein 500
        # (B11). Ein leerer Token ist einfach der falsche Token -- creator_token ist nie leer.
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
        # Ein Bit, keine Zahl: eine Zeile trägt keine Poll-Kennung (F8), "für diese Umfrage" ist
        # also nicht sagbar. Sicher ist nur die Leer-Richtung. Plan §11.7 Punkt 7.
        "mails_pending": OutgoingMail.objects.exists(),
    }
    return render(request, "vote/manage.html", context)


def results(request, poll_identifier):
    poll = get_object_or_404(Poll, identifier=poll_identifier)
    token_state = _token_state(poll)
    if poll.is_active:
        return HttpResponseRedirect(reverse("vote:polls:poll", args=(poll_identifier,)))
    # Einmal auswerten und für Tabelle *und* Diagramm verwenden: `poll.choice_set.all` im Template
    # fragt bei jedem Aufruf neu ab.
    choices = list(poll.choice_set.all())
    # Die Diagrammdaten baut die View, damit das Template sie per `json_script` ausgeben kann statt
    # sie in ein JS-Stringliteral zu interpolieren (B10). Enthaltungen zählen nur bei
    # simple_choice als Segment -- bei multiple_choice hat niemand "nichts" gewählt, dort ist die
    # Summe der Stimmen nicht die Zahl der Wähler.
    chart_series = [{"name": choice.choice_text, "y": choice.votes} for choice in choices]
    if poll.type == PollType.SIMPLE_CHOICE:
        chart_series.append({"name": "Abstentions", "y": token_state["amount_remaining_tokens"]})
    return render(
        request,
        "vote/results.html",
        {"poll": poll, "choices": choices, "chart_series": chart_series, **token_state},
    )
