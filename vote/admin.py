"""Admin-Oberfläche -- absichtlich beschnitten (Review R2-1).

Sie ist seit 2016 registriert, und der User hat bestätigt, dass es in Produktion ein Staff-Konto
gibt. Damit war `/admin/` der einzige Weg im ganzen System, der **Stimmzahlen unmittelbar ändern**
und **jeden Wähler-Token lesen** konnte -- ein Passwort gegen das Kernversprechen. Beides ist hier
zugedreht, ohne die Oberfläche wegzunehmen: nachsehen und aufräumen geht weiter.

Was bewusst **nicht** eingeschränkt ist, und warum: Löschen bleibt erlaubt (eine Umfrage, die
jemand versehentlich oder missbräuchlich angelegt hat, muss wegräumbar sein) und `is_active` bleibt
schaltbar (das kann der Ersteller mit seinem Token auch). Djangos `LogEntry` hält fest, wer was
gelöscht hat.

**Der Rest liegt am Proxy** (notes/to-check.md §B4): `/admin/login/` antwortet ohne jede Drosselung
von Fehlversuchen, und das ist nicht in Django zu lösen, ohne eine Abhängigkeit dazuzunehmen.
"""

from django.contrib import admin

from .models import Choice, Poll, Token


@admin.register(Poll)
class PollAdmin(admin.ModelAdmin):
    list_display = ("title", "type", "is_active", "pub_date", "num_tokens")
    list_filter = ("is_active", "type")
    search_fields = ("title", "identifier")
    # `creator_token` ist ein Geheimnis und gehört nicht auf eine Seite, die ein Passwort öffnet.
    # `exclude` statt `readonly_fields`: letzteres würde ihn weiterhin **anzeigen**.
    exclude = ("creator_token",)
    # Die Kennung steht in jeder Einladungsmail und in jedem Link -- lesbar ist sie also ohnehin,
    # aber änderbar darf sie nicht sein: das bricht alle verschickten Links (Arbeitsregel 5).
    readonly_fields = ("identifier",)


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ("choice_text", "poll", "votes")
    list_filter = ("poll",)
    # **Der wichtigste Riegel:** Stimmzahlen sind nicht editierbar. Sie werden angezeigt, weil ein
    # Staff-Konto sie ohnehin über die Ergebnisseite einer geschlossenen Umfrage sieht -- aber ein
    # Zahlenfeld, das jemand überschreiben kann, ist eine Wahlfälschung in einem Formular.
    readonly_fields = ("votes",)


@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    """Tokens sind sichtbar als *Anzahl*, nie als Wert.

    Wer einen Token liest, kann damit abstimmen -- die Anonymität bleibt gewahrt, aber die Zusage
    „eine Stimme pro Einladung" nicht. Deshalb steht `token_string` weder in der Liste noch im
    Formular.
    """

    list_display = ("__str__", "poll")
    list_filter = ("poll",)
    fields = ("poll",)
    readonly_fields = ("poll",)
