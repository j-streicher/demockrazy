"""Formulare für die Umfrage-Erstellung.

`PollCreateForm` validiert alles, was `/vote/create` annimmt, und ist seit 3.2 von `create()` in
[views.py](views.py) benutzt.

Warum es das Formular gibt: vorher las `create()` direkt aus `request.POST` und prüfte Mailadressen
mit einer selbstgebauten Heuristik. Drei bestätigte Bugs kamen daher und sind mit dem Formular
weggefallen -- ein fehlendes oder unbekanntes Feld endete als 500 statt als Fehlermeldung (B3), eine
ungültige Adresse warf einen ungefangenen `ValidationError` (B12), und doppelt eingetragene Adressen
bekamen doppelte Tokens, dieselbe Person konnte also zweimal abstimmen (B6). Dazu kommt seit 3.8 der
Deckel auf die Empfängerzahl (B4).

Die Feldnamen entsprechen den `name`-Attributen der bestehenden Vorlage; Details dazu am Formular
selbst. Siehe notes/plan.md §7.
"""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .models import PollType


def parse_lines(text):
    """Zerlegt ein Textarea-Feld in getrimmte, nicht-leere Zeilen, Reihenfolge erhalten.

    Ersetzt `parse_choices`/`parse_mails` aus der View. Unterschied zum Bestand: dort wurde an
    Zeilenumbrüchen im engeren Sinne getrennt, sodass ein einzelnes Wagenrücklaufzeichen ohne
    Zeilenvorschub (alte Mac-Konvention) keine Zeilengrenze war. `splitlines()` kennt beide
    Konventionen; für die von Browsern gelieferte Form ist das Ergebnis identisch.
    """
    return [line.strip() for line in text.splitlines() if line.strip()]


class PollCreateForm(forms.Form):
    """Validiert die Eingaben aus `vote/templates/vote/index.html`.

    Die Feldnamen entsprechen exakt den `name`-Attributen des bestehenden Formulars, damit die
    Vorlage unverändert weiterbenutzbar ist und bereits verschickte Links auf `/vote/create`
    weiter funktionieren (Plan-Regel 4).

    `cleaned_data` liefert `choices` und `voter_mails` bereits als Listen, nicht als Rohtext.
    """

    title = forms.CharField(max_length=200)
    type = forms.ChoiceField(choices=PollType.choices)
    description = forms.CharField(widget=forms.Textarea)
    choices = forms.CharField(widget=forms.Textarea)
    creator_mail = forms.EmailField()
    voter_mails = forms.CharField(widget=forms.Textarea)

    def clean_choices(self):
        return parse_lines(self.cleaned_data["choices"])

    def clean_voter_mails(self):
        # dict statt set: die Reihenfolge der Eingabe bleibt erhalten, und der Schlüssel darf
        # von der ausgegebenen Adresse abweichen (siehe Deduplizierung unten).
        accepted = {}
        invalid = []
        for mail in parse_lines(self.cleaned_data["voter_mails"]):
            try:
                validate_email(mail)
            except ValidationError:
                invalid.append(mail)
                continue
            # Deduplizierung gegen B6. Der Schlüssel ist kleingeschrieben: Maildomains sind
            # case-insensitiv, und kein Anbieter vergibt zwei Postfächer, die sich nur in der
            # Groß-/Kleinschreibung unterscheiden. Die erste Schreibweise gewinnt, damit die
            # Mail so rausgeht, wie sie eingegeben wurde.
            accepted.setdefault(mail.lower(), mail)
        if invalid:
            # Alle ungültigen Adressen auf einmal melden -- wer eine Liste von 200 Adressen
            # einfügt, will nicht 200 Anläufe brauchen. Genannt wird nur, was zu beanstanden
            # ist; die gültigen Adressen der Liste tauchen in der Meldung nicht auf.
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
        # Der Deckel gegen B4 (Plan 3.8, F5 entschieden: nur Deckel, kein IP-Rate-Limit).
        # **Nach** der Deduplizierung gezählt: was begrenzt werden soll, ist die Zahl der Mails,
        # und 200 Zeilen mit 150 Dubletten sind 50 Mails.
        #
        # Die Meldung nennt die Grenze und die eigene Zahl, weil der Ersteller sonst raten müsste,
        # wie weit er kürzen soll -- und die Liste steckt bereits im Feld zurück (Plan 3.2).
        if len(accepted) > settings.VOTE_MAX_RECIPIENTS:
            raise ValidationError(
                "At most %(limit)s recipients per poll, got %(count)s.",
                code="too_many_recipients",
                params={"limit": settings.VOTE_MAX_RECIPIENTS, "count": len(accepted)},
            )
        return list(accepted.values())
