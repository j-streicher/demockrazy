import random
import string

from django.db import models
from django.urls import reverse
from django.utils.timezone import now


class PollType(models.TextChoices):
    """Die zwei Abstimmungsarten. Werte unverändert, es sind Spaltenwerte im Bestand."""

    SIMPLE_CHOICE = "simple_choice", "Simple Choice"
    MULTIPLE_CHOICE = "multiple_choice", "Multiple Choice"


def rand_string(length):
    return "".join(
        random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(length)
    )


# Die drei Generatoren haben bis 3.6 nach dem Ziehen geprüft, ob der Wert schon existiert, und sich
# im Kollisionsfall selbst erneut aufgerufen. Das kostete eine Abfrage pro Token -- bei 200
# Empfängern 200 Abfragen und damit der einzige Teil der Umfrage-Erstellung, der noch linear
# wuchs (Plan 3.5). Die Prüfung ist weg, weil sie das Falsche war: sie sah die Geschwister eines
# bulk_create-Batches nicht und konnte die Eindeutigkeit ohnehin nicht garantieren. Erzwungen wird
# sie jetzt von der Datenbank (UniqueConstraint unten). Bei 62^64 bzw. 62^128 möglichen Werten ist
# eine Kollision kein Betriebsfall, sondern ein Grund, am Zufallsgenerator zu zweifeln.
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
            # `identifier` ist der Lookup-Key in jedem Request und wurde immer als eindeutig
            # behandelt -- erzwungen hat es nur niemand. Der Constraint erzeugt auf SQLite
            # implizit `sqlite_autoindex_vote_poll_1`, deckt die Lookups also mit ab; ein
            # zusätzliches `db_index` wäre ein zweiter Index auf derselben Spalte.
            #
            # Achtung, gegen ein Abbild des Prod-Schemas gemessen: SQLite kann keinen Constraint
            # nachträglich anhängen, Django **schreibt die Tabelle dafür neu** (CREATE/INSERT/
            # DROP/RENAME). Für `vote_poll` ändert das nichts weiter, für `vote_token` normalisiert
            # es die 2016er Definitionen mit -- Details in notes/phase-2-migrations.md.
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
            # Alt-Umfragen ohne Empfängerliste: was abgegeben wurde, steht nur in den Choices.
            # Sum() liefert None, wenn es keine gibt.
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
            # Der Token ist das einzige Auth-Merkmal der Stimmabgabe -- Eindeutigkeit gehört in die
            # Datenbank und nicht in eine Vorabprüfung, die sie nicht garantieren kann.
            # Der Tabellen-Neubau (siehe Poll.Meta) macht hier zusätzlich den Fremdschlüssel
            # `DEFERRABLE INITIALLY DEFERRED` und benennt `vote_token_582e9e5a` in
            # `vote_token_poll_id_e1049aa3` um. Beides ist das, was ein frisches `migrate` ohnehin
            # erzeugt; es beseitigt genau die Abweichung, die notes/phase-2-migrations.md als
            # künftiges Risiko notiert hat.
            models.UniqueConstraint(fields=["token_string"], name="vote_token_token_string_unique"),
        ]

    def __str__(self):
        return f"{self.poll} Token"


class OutgoingMail(models.Model):
    """Eine noch nicht verschickte Mail. Die Warteschlange des getakteten Versands (Plan §11.7).

    **Warum es diese Tabelle gibt:** der Mailserver drosselt nach Nachrichten pro Zeitfenster, der
    Versand muss also über Minuten getaktet werden, und das kann nicht im Request passieren. Damit
    braucht die Paarung „welcher Text geht an welche Adresse" einen Ort, der einen Neustart
    übersteht -- sonst verliert ein Restart mitten im Versand die restlichen Einladungen, ohne dass
    jemand sagen kann, welche.

    **Was hier absichtlich *nicht* steht, und das ist der wichtigste Teil (F8, Plan §11.4):**

    * **Keine Poll-Kennung als Spalte** -- kein Fremdschlüssel, nichts, worüber sich Zeilen
      gruppieren lassen. **Der gerenderte Text enthält den Abstimmungslink und damit den
      `identifier`**, und der `recipient` steht daneben: solange die Zeile existiert, sagt sie
      „diese Adresse ist zu dieser Umfrage eingeladen und hat diesen Token". Das ist die mit F8
      bewertete Einbuße (Plan §11.4) und der Grund, warum eine zugestellte Zeile *gelöscht* wird --
      hier stand vorher „eine Zeile sagt für sich nicht, um welche Abstimmung es geht", was für die
      Spalten gilt und für die Zeile nicht (Review R1-1).
    * **Kein Zeitstempel.** Er wäre ein Fingerabdruck: gleiche Sekunde = gleiche Umfrage. Gebraucht
      wird er nicht, die Reihenfolge steckt in der ID und das Aufgeben in `attempts`.
    * **Kein `sent`-Flag und keine Historie.** Eine zugestellte Zeile wird **gelöscht**. Nach dem
      Versand ist der Zustand wieder genau der von vorher.

    Preisgegeben ist damit, solange der Versand läuft, *wer eingeladen wurde* -- **nicht, wie jemand
    gestimmt hat.** Der Token wird bei der Abgabe gelöscht und die Stimme trägt keine Kennung; das
    Kernversprechen bleibt unberührt.
    """

    recipient = models.EmailField()
    # TextField und nicht CharField: die Betrefflänge folgt aus dem Umfragetitel (bis 200 Zeichen)
    # plus Präfix, eine Obergrenze wäre also eine Falle, die SQLite nicht einmal durchsetzt --
    # `bulk_create` validiert nicht. Sortiert oder indiziert wird hier nichts.
    subject = models.TextField()
    body = models.TextField()
    # Zählt **nur** Absagen des Servers für genau diese Nachricht, nicht Verbindungsprobleme.
    # Warum der Unterschied zählt, steht in vote/services/mail.py bei `send_pending()`.
    attempts = models.PositiveSmallIntegerField(default=0)

    def __str__(self):
        # Ohne Adresse: dieselbe Zurückhaltung wie im Logaufruf von `send_pending()` (F8).
        return f"Ausgehende Mail #{self.pk}"
