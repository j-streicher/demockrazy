# Umfassendes Review

> **Status: 7.1 gelaufen, 7.2 abgearbeitet; zweiter Lauf über die Commits danach (§8).**
> 28 Befunde, davon **23 behoben** in 14 Commits --
> ein Commit je Befund bzw. je Befundpaar, die Nummer steht im Betreff. **R2-1 ist zu**: die
> Django-Hälfte behoben (`5adb612`), und der User beschränkt `/admin/` am Proxy aufs Intranet, was
> das fehlende Login-Rate-Limit gegenstandslos macht. Offen sind damit **R8-1** (der User prüft das
> Kennwort vor dem Deploy) und **R9-3** (Verfahrenshinweis, D5). Was **noch nicht geprüft** ist, steht
> unverändert in §7. Angelegt 2026-08-04.
>
> Geplant in [plan.md](plan.md) §14. Befunde kommen hierher, Handlungspunkte außerhalb des Repos
> nach [to-check.md](to-check.md).
>
> **Baseline zu Beginn des Laufs gemessen:** `pytest` → 215 passed, Arbeitsbaum sauber,
> 80 Commits über `master`. **Nach 7.2:** `pytest` → **253 passed**,
> `check --fail-level WARNING` → no issues, `makemigrations --check` → No changes, ruff sauber.
> **Nach dem Nachzug von R2-1:** `pytest` → **261 passed**.
> **Nach R10-4** (Nachtrag, gefunden nach 7.2): `pytest` → **262 passed**.
> **Zweiter Lauf (§8), 2026-08-14:** drei neue Befunde -- **R15-2** (Mittel), **R10-5**, **R15-3** --
> alle **offen**, denn Regel 3 gilt auch für den zweiten Lauf: gemessen, aufgeschrieben, nicht behoben.

---

## 1. Umfang

**Der ganze Branch: `master..HEAD`, 78 Commits, plus der Ist-Zustand.**

Beides, und das ist Absicht: ein Diff zeigt Änderungen, aber nicht, was jemand *nicht* geändert hat
und hätte ändern müssen; ein Blick nur auf den Endzustand übersieht, was unterwegs eingeschleppt
wurde. Konkret:

- der Anwendungscode (`vote/`, `demockrazy/`), Templates, Migrations, Management-Command
- die Testsuite selbst — **Tests sind Prüfgegenstand, nicht Prüfinstanz** (§2, Regel 4)
- Konfiguration: `settings.py`, `dev_settings.py`, `test_settings.py`, `pyproject.toml`, `flake.nix`,
  `.gitignore`, CI-Workflow
- die vendorten Assets samt `PROVENANCE.md`
- die Notizen — auf Richtigkeit, nicht auf Vollständigkeit
- die **Deployment-Schnittstelle**: alles, was still verlorengehen kann, weil `demockrazy_config`
  Einstellungen überschreibt (die B16-Klasse von Fehlern)

**Außerhalb des Umfangs, weil ich es nicht sehen kann** (Arbeitsregel 10): das NixOS-Modul, das
Colmena-Repo, der Proxy-vhost, die Prod-Node. Was dort zu prüfen wäre, wird als Frage formuliert und
landet in [to-check.md](to-check.md), nicht als Befund hier.

## 2. Vorgehen — fünf Regeln, die das Review überhaupt erst belastbar machen

1. **Ich habe das alles selbst geschrieben.** Ein Review der eigenen Arbeit ist wertlos, wenn es
   bestätigen will. Die Gegenmaßnahme ist keine Haltung, sondern eine Liste: §3 zählt die
   Fehlerklassen auf, die in *diesem* Projekt schon real vorgekommen sind. Sie werden gezielt
   gesucht, nicht abgewartet.
2. **Jeder Befund ist entweder gemessen oder als ungemessen markiert.** Kein „könnte
   problematisch sein". Entweder steht eine Reproduktion dabei (Befehl, Testfall, Zahl) oder
   ausdrücklich **„gelesen, nicht gemessen"**. Beides ist zulässig, das Vermischen nicht.
3. **Keine Reparatur während des Reviews.** Wer im Vorbeigehen behebt, verliert den Nachweis, dass
   es den Befund gab, und hört auf zu suchen. Erst die vollständige Liste, dann eigene Commits pro
   Befund — mit Verweis auf die Nummer hier.
4. **Negativraum wird protokolliert.** Zu jedem Kriterium steht am Ende, *wie* geprüft wurde, auch
   wenn nichts gefunden wurde. Ein Review ohne diesen Teil ist nicht nachprüfbar: „keine Befunde"
   und „nicht hingesehen" sehen sonst gleich aus.
5. **Wo ich das Ergebnis nicht kenne, wird gemessen, nicht geschlossen.** Das ist Arbeitsregel 4 und
   hat in diesem Projekt mehrfach falsche Schlüsse verhindert.

## 3. Die Fehlerklassen dieses Projekts — gezielt zu suchen

Nicht abstrakt, sondern was hier **schon passiert ist**. Die beste Vorhersage für den nächsten Fehler
ist der letzte:

| # | Klasse | Wo sie herkommt |
|---|---|---|
| K1 | **Still wirkungslose Konfiguration** — steht da, wird nie gelesen | B16 (`ATOMIC_REQUESTS` zehn Jahre modulweit), 5.4 (SQLite-`OPTIONS` gehen über `demockrazy_config` verloren) |
| K2 | **Template-Fallen, die keinen Fehler erzeugen** | B17 (mehrzeilige `{# #}`) — sauberer 200, kaputte Seite, `curl` sah gut aus |
| K3 | **Werkzeug schluckt etwas stillschweigend** | B18 (`.gitignore: static/` verschluckte Assets), `git add` verweigerte ohne `-f` |
| K4 | **Prüfung, die nicht prüft** | Die erste Phase-0-Sonde meldete „IDENTISCH" auf zwei identischen Tracebacks |
| K5 | **Buchhaltungsfehler in eigener Logik** | Der `deferred`-Zähler im ersten Entwurf von `send_pending()` rechnete kumulative Summen gegen eine Batchgröße |
| K6 | **Plausibel begründet und trotzdem falsch** | „Gemeinsame SMTP-Verbindung behebt das Rate-Limit" — sie behebt es nicht; „B legt die Abstimmung still" — tut es erst jenseits des Timeouts |
| K7 | **Framework-Default anders als erwartet** | `EMAIL_TIMEOUT = None` heißt unbegrenzt; `inherit environment` kollidiert mit `environment.PATH` |
| K8 | **Verhaltensänderung, die niemand bestellt hat** | Regel 3/6: Mail-Wortlaut, Token-Längen, URL-Struktur, Feldnamen |

## 4. Kriterien

Reihenfolge ist die Prüfreihenfolge: das Kernversprechen zuerst, Kosmetik zuletzt.

| # | Bereich | Was konkret geprüft wird |
|---|---|---|
| R1 | **Anonymität** (das Kernversprechen) | Gibt es *irgendeinen* Weg von einer Stimme zu einem Wähler? Warteschlange, Token-Cookie, Logs, `django_session`, Migrations-Artefakte, Backups. Was verrät ein Angreifer mit Leserechten auf die DB *während* eines Versands, was danach? |
| R2 | **Authentifizierung / Autorisierung** | Wähler-Token und Management-Token: Erzeugung (Entropie, `SystemRandom`), Vergleich, Verbrauch, Wiederverwendung. Der Cookie-Pfad. Was ohne Token erreichbar ist und ob das gewollt ist (Manage-Seite, `/healthz`, `/vote/create`) |
| R3 | **Eingabeprüfung / Injection** | ORM-Nutzung auf rohes SQL, Template-Autoescaping (**inkl. der Mail-Templates, wo es absichtlich aus ist**), `json_script`, Header-Injection im Mail-Betreff, der eigene URL-Converter, Redirect-Ziele |
| R4 | **Nebenläufigkeit / Datenintegrität** | Vier uwsgi-Prozesse auf einer SQLite-Datei, Versender gegen Stimmabgabe, `F()`-Ausdrücke, `atomic()`-Grenzen, die zwei `UniqueConstraint`s, doppelter Versand, die `flock` (auch: kann sie hängenbleiben?) |
| R5 | **Fehlerbehandlung** | Jedes `except`: was wird geschluckt, was gelogt, was erfährt der Nutzer. Kein Pfad in einen 500. Was passiert bei Ausfall von SMTP, Datenbank, Plattenplatz |
| R6 | **Informationslecks** | Fehlerseiten, Logzeilen (**Adressen? Tokens?**), der 503-Body von `/healthz`, das neue `mails_pending`-Bit, Security-Header |
| R7 | **Missbrauch / DoS** | `/vote/create` ohne Auth: Empfänger-Deckel, aber auch Umfrage-Anzahl, Textlängen, Warteschlangenwachstum, `EMAIL_TIMEOUT`, Laufzeit des Versenders |
| R8 | **Geheimnisse** | `SECRET_KEY`-Pfad und Fallback, nichts Geheimes im Repo, Cookie-Flags, was in Logs und Tracebacks landet |
| R9 | **Migrations & Deploy-Sicherheit** | `0001`–`0004` gegen den Prod-Stand, Reihenfolge, Rückwärtsweg, `preStart`-Verhalten, **die K1-Klasse**: welche Einstellung geht über `demockrazy_config` still verloren |
| R10 | **Testabdeckung und Testqualität** | Was ist *nicht* abgedeckt. Welcher Test besteht auch bei kaputtem Code (K4). Prüfen Tests Wirkung oder Implementierung. Sind die Fixtures ehrlich |
| R11 | **Performance** | Query-Zahlen pro View, N+1, die Warteschlangen-Abfrage, Umfrage-Erstellung bei 150 Empfängern, die Ergebnisseite |
| R12 | **Lieferkette / Lizenzen** | Vendorte Assets gegen `PROVENANCE.md`, die absichtlichen Änderungen daran, nixpkgs-Pinning, CI-Actions, alles MIT/Apache |
| R13 | **Barrierefreiheit** | Formulare, Labels, `aria-*`, das Canvas der Ergebnisseite, Tastaturbedienung, Kontrast |
| R14 | **Lesbarkeit / Wartbarkeit** | Namen, toter Code, Duplikate, **Kommentarlänge** (die Präferenz ist kurz), irreführende Docstrings |
| R15 | **Dokumentation** | README und `notes/` gegen den Code — Stellen, die etwas behaupten, was nicht mehr gilt |

## 5. Befunde

Was hier steht, ist gemessen; was noch fehlt, steht in §7 („noch nicht geprüft").

**Jede Behebung ist gegengeprüft:** der alte Zustand wurde wiederhergestellt und der neue Test
gefahren -- ein Test, der auch ohne die Behebung besteht, wäre Fehlerklasse K4 und hier fehl am
Platz. Bei **R4-1** ist zusätzlich die Threads-Messung wiederholt: vorher 4 von 100 Runden mit zwei
Stimmen, danach **0 von 100**. Die Template-Änderungen sind **im Browser** nachgesehen (Lehre aus
B17: `pytest` und `curl` sehen Markup-Fallen nicht).

**24 Befunde, nach Schwere.** Die Reihenfolge dieser Tabelle ist die Lesereihenfolge; im Text
darunter stehen sie gruppiert nach Kriterium. *(Beim Abarbeiten in 7.2 nachgezählt: die Tabelle
listete zuerst 23 und ließ R14-3 aus, das als Befund darunter stand. Korrigiert -- der Commit
`b50f5a4` und die erste Zusammenfassung an den User nennen deshalb 23.)*

Sie war die **Arbeitsliste für 7.2** und trägt jetzt das Ergebnis. „Klasse" verweist auf die
Fehlerklassen in §3. **Alle 24 sind gemessen**, kein „gelesen, nicht gemessen" -- mit einer
benannten Ausnahme: bei R2-1 ist die Oberfläche gemessen, die Existenz von Konten in Prod nicht
(Arbeitsregel 10).

| # | Schwere | Befund | Ort | erledigt |
|---|---|---|---|---|
| **R4-1** | **kritisch** | Zwei gleichzeitige POSTs mit demselben Token = **zwei Stimmen** (4 von 100 Runden, beide 302) | [views.py:208](../vote/views.py:208) | `a1b5117` -- Löschung ist die Bedingung, Abfrage in der Transaktion. **0 von 100** statt 4 von 100 |
| **R5-1** | **hoch** · K5, K7 | Ein `\n` im Titel macht die vorderste Warteschlangenzeile unversendbar → `BadHeaderError` ungefangen → Versand **aller** Umfragen steht dauerhaft | [forms.py:46](../vote/forms.py:46), [mail.py:113](../vote/services/mail.py:113) | `af30fa5` -- Umbruch abgelehnt **und** unversendbare Zeile als `PERMANENT`; das Test-Double baut die Nachricht jetzt wirklich |
| **R2-1** | **hoch** | `/admin/` geroutet, `creator_token` lesbar, `Choice.votes` editierbar, kein Login-Rate-Limit -- **es gibt ein Staff-Konto** (User, 2026-08-04) | [admin.py](../vote/admin.py) | `5adb612` im Repo (`votes` nicht editierbar, Tokens nicht lesbar) **+ Proxy beschränkt `/admin/` aufs Intranet** (User, 2026-08-04) -- damit zu |
| R3-1 | mittel · K7 | `?token=` geht ungeprüft in `set_cookie()`: Steuerzeichen → `CookieError`/**500**, Nicht-Latin-1 → Header, der nicht WSGI-konform ist | [views.py:56](../vote/views.py:56) | `4d6e003` -- `_looks_like_a_token()` vor `set_cookie()` |
| R7-1 | mittel | Nur die Empfängerzahl ist gedeckelt: 200 000 Zeichen Beschreibung und 5 000 Choices gehen durch (1,3 MB Antwort) | [forms.py:46](../vote/forms.py:46) | `3e89f0c` -- `max_length` 10 000/20 000 und `VOTE_MAX_CHOICES` = 100 (**Wert von mir**, siehe Commit) |
| R9-1 | mittel · K1 | Der Härtungs-Check prüft `transaction_mode` nur auf Anwesenheit -- `DEFERRED` und `"quatsch"` kommen durch, `timeout: 0` auch | [checks.py:57](../demockrazy/checks.py:57) | `a2b50d4` -- Wert statt Anwesenheit, bei allen drei Optionen |
| R9-2 | mittel · K1 | Der Check ist ein `Warning`: `manage.py check` endet mit **0**, die CI bleibt grün, die Suite sieht ihn nie | [checks.py:63](../demockrazy/checks.py:63), [checks.yml:47](../.github/workflows/checks.yml:47) | `a2b50d4` -- CI mit `--fail-level WARNING`; `Error` bleibt **deine** Entscheidung (D2) |
| R10-1 | mittel · K4 | `test_the_page_varies_on_cookie` besteht auch ohne `@vary_on_cookie` -- den Header setzt die CSRF-Middleware | [test_views.py:406](../vote/tests/test_views.py:406) | `eff438f` -- gegen die zwei Redirects geprüft, wo kein Formular den Header setzt |
| R10-2 | mittel · K1 | Kein Test deckt, dass Tokens aus einem CSPRNG kommen -- `random.choice` statt `SystemRandom` bleibt unbemerkt | [models.py:16](../vote/models.py:16) | `eff438f` -- gleicher Startwert, trotzdem verschiedene Tokens |
| R1-1 | niedrig · K6 | Der `OutgoingMail`-Docstring sagt „keine Poll-Kennung" -- der `body` enthält Link, `identifier` und Token | [models.py:126](../vote/models.py:126) | `4282901` -- Docstring und README richtiggestellt |
| R1-2 | niedrig | Token-`id`s stehen in Empfängerreihenfolge: wer die Liste hat und die DB liest, sieht **wer** abgestimmt hat (Stimme bleibt unverknüpfbar) | [polls.py:38](../vote/services/polls.py:38), [mail.py:277](../vote/services/mail.py:277) | `8c65cd3` -- `SystemRandom().shuffle()` vor der Paarung |
| R6-1 | niedrig · K6 | Abgelehnte Mail: eine Logzeile ohne SMTP-Code und ohne Grund -- und der Kommentar daneben behauptet, `logger.exception` protokolliere die Adresse | [mail.py:237](../vote/services/mail.py:237) | `6363cb1` -- SMTP-Code im Log, Kommentar korrigiert |
| R13-1 | niedrig | Alle sechs Seiten heißen „Demockrazy" -- `{% block title %}` wird von keiner Vorlage gefüllt | [base.html:15](../vote/templates/base.html:15) | `decb33b` -- alle sechs Vorlagen füllen den Block, im Browser nachgesehen |
| R13-2 | niedrig | Formularfehler erscheinen in Body-Farbe als Aufzählung, während dieselbe Anwendung Abstimmungsfehler rot zeigt | [index.html:24](../vote/templates/vote/index.html:24) | `decb33b` -- `.errorlist` in `main.css`; Kontrast gemessen 4,53:1 (AA knapp bestanden) |
| R14-1 | niedrig | „Total Voters: **None**" bei Alt-Umfragen ohne `num_tokens` | [results.html:26](../vote/templates/vote/results.html:26) | `decb33b` -- `amount_tokens_total` |
| R14-2 | niedrig · K5 | Vier Kommentare beschreiben einen überholten Stand (`deferred`-Schlüssel, `deliver()`/`on_commit`, „Bootstrap 3", falscher Pfad in `PROVENANCE`) | mail.py:165 + :273, index.html:4, chartjs/PROVENANCE.md | `4282901` + `8c65cd3` -- alle vier Stellen |
| R15-1 | niedrig | Die README beschreibt die Suite von vor 3.8 (`xfail(strict=True)`), nennt vier `DEMOCKRAZY_*`-Variablen nicht und wiederholt den Fehler aus R1-1 | [README.md:52](../README.md:52) | `4282901` -- xfail, Variablenliste, Warteschlangen-Satz, `--fail-level` |
| R5-2 | Notiz | Kein Wächter in `while True:` -- eine Mutation schickte die Suite in eine Endlosschleife, die die `flock` für immer hält | [mail.py:194](../vote/services/mail.py:194) | `6363cb1` -- Wächter auf die vorderste `pk` |
| R6-2 | Notiz | Die Seite mit dem Token trägt kein `Cache-Control` (nur `Vary: Cookie`) | [views.py:79](../vote/views.py:79) | `5ddd491` -- `@never_cache` auf `poll()` und `manage()` |
| R8-1 | Notiz | sops-Geheimnisse von 2023 (`email_password`) stehen weiter in der History -- gelöscht ≠ rotiert | `master:k8s/…/secrets.sops.yaml` | **offen** -- Frage an den User (A5); Rotation statt History umschreiben |
| R9-3 | Notiz | Rückwärts-Migration hinter `0004` wirft die Warteschlange weg → Tokens ohne Einladung | [0004](../vote/migrations/0004_outgoingmail.py) | **offen als Verfahren** -- to-check.md D5, kein Codeeingriff |
| R10-3 | Notiz · K4 | Drei weitere unbemerkte Mutationen: Taktungs-Defaults (30/2) ungeprüft, `multiple_choice`-Diagrammdaten ungeprüft | vote/tests/ | `eff438f` -- Taktungswerte 30/2 und das multiple_choice-Diagramm |
| R10-4 | **Mittel** · K4 | Das Mail-Double erzeugt den `450` in der falschen smtplib-Form — der Zweig, den ein echter drosselnder Server trifft, ist von keinem Test gedeckt | [test_mail_service.py:234](../vote/tests/test_mail_service.py:234), [mail.py:106](../vote/services/mail.py:106) | siehe unten |
| R11-1 | Notiz | `multiple_choice`: ein `UPDATE` je Choice **unter der Schreibsperre** (17 Abfragen bei 10 Choices) | [views.py:194](../vote/views.py:194) | `5ddd491` -- ein `UPDATE` per `filter(pk__in=...)` |
| R14-3 | Notiz | `get_amount_used_unused()` viermal mit demselben Dreizeiler entpackt | [views.py:100](../vote/views.py:100) | `9bf0fc7` -- ein `_token_state(poll)`-Helfer, kein Verhaltens- und kein Abfrageunterschied |
| R15-2 | **Mittel** · K6 | Die Anleitung zum Fake-Mailserver funktioniert nicht: der Trap setzt sein Fenster nie zurück, der zweite Lauf verschickt nichts | [README.md](../README.md), [handover.md](handover.md) §7 | **offen** |
| R10-5 | Notiz · K4 | Das neue Double zählt eine abgebrochene `DATA` als zugestellt, mischt Nachrichten- und Empfängerzähler und verschluckt eigene Fehler | [mailtrap.py](../vote/tests/mailtrap.py) | **offen** |
| R15-3 | Notiz | Die R10-4-Zeile dieser Tabelle nennt „siehe unten" statt ihres Commits | review.md:142 | **offen** |

Zwei Muster fallen daran auf, und sie sind der eigentliche Ertrag des Laufs:
**(1) Das Gefährliche stand nicht im Code, sondern in seinen Rändern** -- der Doppelklick, der
Zeilenumbruch, der krumme Query-Parameter. Die Logik selbst hielt jedem Angriff stand, den ich
gefahren habe.
**(2) Die Prüfungen, die gegen K1 gebaut wurden, haben selbst K1** -- der Härtungs-Check prüft nicht
den Wert (R9-1) und macht nichts rot (R9-2), und ein Test prüft einen Header, den ein anderer
Mechanismus setzt (R10-1). Wer eine Gegenmaßnahme baut, muss sie kaputtmachen, um zu wissen, ob sie
greift; genau das hat die Mutationssonde geleistet.

### R4-1 · Ein Doppelklick auf „Vote" ergibt zwei Stimmen aus einem Token

**Schwere:** **kritisch** (verfälscht Stimmen -- die Definition in §5 unten)
**Ort:** [../vote/views.py:208](../vote/views.py:208) -- die Token-Abfrage steht **vor**
`with transaction.atomic():`, das `delete()` darin.
**Nachweis:** **gemessen.** Zwei echte gleichzeitige `POST …/vote` mit demselben Token, an einer
Barriere synchronisiert, 100 Runden, Datei-SQLite mit der Prod-Härtung aus 5.4
(`transaction_mode=IMMEDIATE`, `timeout=20`, WAL):

```
DOPPELT: votes=2 tokens_left=0 is_active=False statuscodes=[302, 302]
… (4 solche Runden)
ERGEBNIS: 4 von 100 Runden mit zwei Stimmen aus einem Token
```

Beide Anfragen antworten mit **302 auf die Erfolgsseite**. Die Umfrage hatte `num_tokens=1`.

**Befund:** `vote()` liest den Token **außerhalb** der Transaktion:

```python
token = Token.objects.get(token_string=token_string, poll=poll)   # außerhalb
...
with transaction.atomic():
    record_simple_choice()      # votes = F("votes") + 1
    token.delete()              # löscht 0 Zeilen, wenn schon weg -- ohne Fehler
```

Zwei Anfragen lesen dieselbe Zeile, dann laufen ihre `atomic()`-Blöcke -- durch `IMMEDIATE`
serialisiert, was hier nicht hilft: der zweite Block zählt mit `F("votes") + 1` **auf den bereits
erhöhten Wert** und ruft `delete()` auf eine Zeile, die es nicht mehr gibt. Django wirft dabei
nicht, `delete()` auf eine verschwundene Zeile ist ein stiller No-op. Die Serialisierung verhindert
`SQLITE_BUSY`, nicht die doppelte Buchung: es fehlt eine Prüfung, ob dieser Verbrauch **derjenige
war, der den Token entfernt hat**.

**Folge:** Die Zahl der Stimmen kann die Zahl der Wähler übersteigen; die Ergebnisseite zeigt dann
`a: 2` bei `Total Voters: 1`. Kein Angriff nötig -- ein Doppelklick auf den Absenden-Knopf oder ein
Reload-nach-POST reicht, und der Wähler sieht zwei Mal „successful", merkt also nichts. Damit ist es
der einzige gefundene Weg, ein Ergebnis zu verfälschen. Die Anonymität bleibt unberührt.

**Nicht gemessen und ausdrücklich offen:** wie viele Stimmen ein *absichtlicher* Angreifer aus einem
Token holt. Der Versuch mit 10 parallelen Anfragen brachte in der Testumgebung
`OperationalError: database table is locked` aus dem pytest-Harness (die Testtransaktion des
Haupt-Threads hält die Tabelle), gezählt wurden dort trotzdem 2 Stimmen. Belastbar ist deshalb nur
die Zwei-Anfragen-Messung; „mehr als 2 sind unmöglich" ist **nicht** gezeigt.

**Warum die Testsuite das nicht sah** (K4, Regel: Tests sind Prüfgegenstand): sie prüft „Token wird
verbraucht" und „Token zweimal *nacheinander* schlägt fehl" -- beides hält. Der Fall ist
*gleichzeitig*, und dafür gibt es keinen Test. `TestAnonymity` deckt ihn nicht ab, weil er die
Anonymität gar nicht berührt.

**Vorschlag:** den Verbrauch zur Bedingung machen statt zur Nebenwirkung -- die Abfrage in den
`atomic()`-Block ziehen und den Token **zuerst** löschen, und zwar an der Löschung entscheiden:
`deleted, _ = Token.objects.filter(pk=token.pk).delete()`, und nur bei `deleted == 1` die Stimme
buchen. Alternativ `select_for_update()`, das SQLite aber nur innerhalb einer Transaktion und ohne
echte Zeilensperre umsetzt -- die Löschung als Bedingung ist der Weg, der auf SQLite trägt. Ein
Regressionstest gehört dazu: zwei Threads an einer Barriere, wie in der Sonde.
Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `a1b5117`**.

### R3-1 · `?token=` landet ungeprüft in einem Cookie — zwei Wege in einen 500

**Schwere:** mittel
**Ort:** [../vote/views.py:56](../vote/views.py:56) -- `token = request.GET["token"]`, direkt weiter
an `response.set_cookie(...)`
**Nachweis:** **gemessen**, jeweils ein einzelner unauthentifizierter `GET /vote/<id>/?token=…`:

*Fall a -- Steuerzeichen:*

```
GET /vote/<id>/?token=a%0D%0ASet-Cookie:%20admin=1
→ http.cookies.CookieError: Control characters are not allowed in cookies
  'vote_token' 'a\r\nSet-Cookie: admin=1' '"a\\015\\012Set-Cookie: admin=1"'
ERROR django.request: Internal Server Error: /vote/<id>/
```

*Fall b -- Zeichen jenseits von Latin-1:*

```
GET /vote/<id>/?token=✓
Set-Cookie: vote_token="✓"; expires=…; HttpOnly; Max-Age=2592000; Path=/vote/…
latin-1-kodierbar (WSGI-Anforderung): NEIN
  -> 'latin-1' codec can't encode character '✓' in position 24
```

Zum Vergleich mitgemessen: `äöü` ist unkritisch (Python oktal-escapet es zu `\344\366\374`), und
8 000 Zeichen setzen ein 8 000 Zeichen langes Cookie, ohne dass serverseitig etwas bricht.

**Befund:** Der Wert aus dem Query-String geht **ohne jede Prüfung** in `set_cookie()`, obwohl das
Format eines echten Tokens exakt bekannt ist (`[A-Za-z0-9]{128}`, `mk_token()`) -- für die
Umfragekennung in derselben URL erzwingt `urls.py` genau diese Zeichenklasse mit einem eigenen
Converter, für den Token daneben tut es niemand.
*Fall a:* Pythons `http.cookies` verweigert Steuerzeichen und wirft `CookieError`. **Keine
Header-Injection** -- die Bibliothek verhindert sie, und selbst der Escape-Weg (`\015\012`) wäre
harmlos --, aber die Ausnahme wird nirgends gefangen: **HTTP 500** auf einem GET, den jeder
absetzen kann.
*Fall b:* Der Set-Cookie-Header enthält ein Zeichen, das nach PEP 3333 nicht in einen
WSGI-Header darf. Django selbst wirft hier nicht (der Test-Client liefert 302 und
`serialize_headers()` sieht die Cookies nicht), der Fehler entsteht eine Schicht tiefer: der
folgende Request des Test-Clients stirbt an
`UnicodeEncodeError` in `django.core.handlers.wsgi.get_str_from_wsgi`. **Was uwsgi damit macht, ist
von hier nicht gemessen** -- entweder ein Fehler beim Schreiben des Headers oder ein verstümmeltes
Cookie. Ein echter Browser käme mit dem zurückgeschickten Cookie nicht in denselben
`UnicodeEncodeError` (er schickt Bytes, und die sind latin-1-abbildbar); der Ausgangs-Request bleibt
das Problem.

**Folge:** Ein 500 statt einer Fehlerseite auf einem Pfad, für den dieser Branch fünf andere 500er
beseitigt hat (B2, B3, B11, B12, B15). Kein Datenverlust, keine Injection, keine Persistenz -- aber
es ist genau das Kriterium **R5** („Kein Pfad in einen 500"), und der Weg dorthin ist ein
angetippter Link. Fehlerklasse **K7**: `set_cookie` sieht harmlos aus, und dass die
Standardbibliothek darin eine Ausnahme wirft, steht in keiner Django-Doku, die man hier gelesen
hätte.

**Warum die Testsuite das nicht sah:** `TestTokenLeavesTheUrl` prüft den Umzug mit *echten* Tokens
und mit dem leeren Wert -- die zwei Fälle, die im Betrieb vorkommen. Krumme Werte prüft nichts;
`test_views.py` hat für die Umfragekennung eine solche Prüfung (`TestUrls` gegen den Converter), für
den Token nicht.

**Vorschlag:** den Wert vor dem Setzen gegen `[A-Za-z0-9]+` und eine Längenobergrenze prüfen und
alles andere wie „kein Token" behandeln (also den `delete_cookie`-Zweig nehmen, der schon existiert).
Das ist eine Zeile und deckt beide Fälle plus die 8 000-Zeichen-Variante ab. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `4d6e003`**.

### R5-1 · Ein Zeilenumbruch im Umfragetitel legt den **gesamten** Mailversand still

**Schwere:** hoch (an der Grenze zu kritisch, Begründung unten)
**Ort:** [../vote/forms.py:46](../vote/forms.py:46) (nimmt ihn an) ·
[../vote/services/mail.py:113](../vote/services/mail.py:113) (`_send_one` fängt ihn nicht) ·
[../vote/templates/vote/mail/creator_subject.txt](../vote/templates/vote/mail/creator_subject.txt)
**Nachweis:** **gemessen**, Sonde gegen die echte Kette `POST /vote/create` → `send_pending()`:

```
CREATE STATUS: 200
QUEUE: 3 POLLS: 1
RAISED: BadHeaderError Header values can't contain newlines
        (got "[democrazy] Poll 'Kaffee\nBcc: leak@example.org' created" for header 'Subject')
QUEUE LEFT: 3 OUTBOX: 0
```

**Befund:** `PollCreateForm.title` ist ein `CharField` ohne Prüfung auf Zeilenumbrüche -- Django
strippt nur außen. Der Titel geht unverändert in `creator_subject.txt` (`{% autoescape off %}`),
`_render()` macht nur `.strip()`, und der Umbruch bleibt **innen** stehen. Beim Versand wirft
Djangos `forbid_multi_line_headers` einen `BadHeaderError`. Der ist eine `ValueError`-Unterklasse
und wird von `_send_one()` **nicht** gefangen -- dort stehen `UnicodeEncodeError`, `SMTPException`,
`OSError` und die zwei SMTP-Antwortfehler. Die Ausnahme fliegt durch `_send_batch()` und
`send_pending()` bis in den Management-Command und beendet ihn mit Traceback.

**Folge:** Die vergiftete Zeile ist die **erste** der Umfrage (Erstellermail, `order_by("pk")`) und
wird nie gelöscht. Jeder folgende Timer-Aufruf greift sie erneut und stirbt an derselben Stelle:
**ab diesem Moment geht keine Mail mehr raus, auch nicht die anderer Umfragen** -- die Warteschlange
ist global. Ein einzelner unauthentifizierter POST hält den Versand des ganzen Dienstes dauerhaft an,
und zwar still: die Erstellerseite sagt „The invitations are on their way", die Manage-Seite sagt
korrekt „Invitations are still queued", nur eben für immer. Aufräumen geht nur per Hand in der
Datenbank auf der Prod-Node.
Kein Header-Injection: Django blockt den Umbruch, es wird **kein** `Bcc` gesetzt. Die Schwere kommt
allein vom Stillstand.
**Nicht kritisch nach der Skala in §5**, weil keine Stimme verloren geht oder verfälscht wird und
die Anonymität unberührt bleibt -- aber es ist der teuerste „hoch": Betriebsausfall der
Kernfunktion, von außen auslösbar, ohne Selbstheilung.
Klasse **K5** (Buchhaltung im eigenen Fehlerpfad: `attempts` deckt 4xx/5xx ab, aber nicht „diese
Zeile ist überhaupt nicht verschickbar") und **K7** (`BadHeaderError` erbt von `ValueError`, nicht
von `SMTPException`).

**Vorschlag:** zwei Stellen, unabhängig voneinander nützlich. (a) Im Formular Umbrüche im `title`
ablehnen oder ersetzen -- der Titel steht in einem Mail-Betreff, dort gehört keiner hin. (b) In
`_send_one()` einen Fangzweig, der eine **nicht verschickbare** Zeile als `PERMANENT` behandelt
statt den Lauf zu töten; nur so kann eine einzelne kaputte Zeile nie wieder alle anderen aufhalten.
Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `af30fa5`**.

### R9-1 · Der Check gegen stille Fehlkonfiguration prüft `transaction_mode` nicht auf den Wert

**Schwere:** mittel
**Ort:** [../demockrazy/checks.py:57](../demockrazy/checks.py:57)
**Nachweis:** **gemessen**, `problems_for()` mit prod-artiger Config:

```
DEFERRED PROBLEMS: []      # transaction_mode="DEFERRED", timeout=0
GARBAGE PROBLEMS: []       # transaction_mode="quatsch"
```

**Befund:** `if not options.get("transaction_mode")` prüft nur auf *irgendeinen* Wert. `DEFERRED`
ist Djangos Default und genau der Zustand, den 5.4 abgeschafft hat (gemessen: 164 von 200
gleichzeitigen Stimmabgaben scheitern); der Check meldet ihn nicht. Ein Tippfehler wie `"quatsch"`
kommt ebenso durch -- SQLite bekäme dann von Django ein `BEGIN quatsch` und der Verbindungsaufbau
schlägt fehl, aber der Check sagt vorher nichts. Dasselbe eine Zeile höher: `"timeout" not in
options` lässt `timeout: 0` passieren, also *keine* Wartezeit.

**Folge:** Der Check existiert genau gegen K1 („steht da, wirkt nicht") und hat selbst ein
K1-Loch. Übernimmt jemand die `OPTIONS` ins NixOS-Modul und schreibt dabei `DEFERRED` oder
verschreibt sich, bleibt `manage.py check` still -- und die `database is locked`-Fehler aus B13
sind zurück, ohne Vorwarnung. Das ist der Fall, für den der Check gebaut wurde.

**Vorschlag:** auf den Wert prüfen (`== "IMMEDIATE"`, case-insensitiv) und beim `timeout` einen
positiven Wert verlangen. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `a2b50d4`**.

### R9-2 · Der Check ist ein `Warning`, und damit fällt kein einziges Gate darüber

**Schwere:** mittel
**Ort:** [../demockrazy/checks.py:63](../demockrazy/checks.py:63) ·
[../.github/workflows/checks.yml:47](../.github/workflows/checks.yml:47)
**Nachweis:** **gemessen** -- `transaction_mode` aus `settings.py` entfernt, dann die CI-Zeile
gefahren:

```
WARNINGS:
?: (demockrazy.W001) DATABASES['default'] ist SQLite auf einer Datei, ohne die Härtung …
System check identified 1 issue (0 silenced).
EXITCODE: 0
```

Und dieselbe Entfernung gegen die Testsuite, per Mutation:

```
UNBEMERKT  SQLite transaction_mode entfernt -> 215 passed in 4.18s
UNBEMERKT  SQLite journal_mode entfernt    -> 215 passed in 4.00s
```

**Befund:** `manage.py check` beendet sich bei `Warning` mit **0**; erst `ERROR` macht einen
Rückgabecode ungleich null (oder `--fail-level WARNING`). Die CI ruft es ohne Zusatz auf. Die
Testsuite kann es ohnehin nicht sehen: sie läuft auf `:memory:`, wo der Check absichtlich nicht
greift, und `demockrazy/tests/test_checks.py` prüft die *Funktion* `problems_for()`, nicht die
tatsächlichen Settings.

**Folge:** Geht die Härtung verloren -- im Repo oder im NixOS-Modul --, meldet es nichts, was einen
Bau rot macht. Der Text wird gedruckt und verschwindet im Log, genau wie bei den zwei Vorbildern
B16/B18. Die Notizen führen den Check als Gegenmaßnahme gegen K1
([handover.md](handover.md) §11 letzter Punkt); als Gate ist er keine.
Zusammen mit **R9-1** heißt das: von den drei Optionen wird nur die Anwesenheit zweier Namen
geprüft, und selbst dieser Befund bleibt folgenlos.

**Vorschlag:** entweder `Error` statt `Warning` (dann bricht `check` von selbst ab, auch im
`preStart` in Produktion -- das ist der Ort, an dem es zählt), oder in der CI
`manage.py check --fail-level WARNING`. Ersteres ist strenger und trifft Produktion mit, letzteres
ändert das Verhalten des Dienstes nicht. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `a2b50d4`**.

### R6-1 · Die Logzeile einer dauerhaft abgelehnten Mail nennt keinen Grund — und der Kommentar daneben behauptet das Gegenteil

**Schwere:** niedrig
**Ort:** [../vote/services/mail.py:237](../vote/services/mail.py:237)
**Nachweis:** **gemessen** -- Verbindung durch eine ersetzt, die
`SMTPRecipientsRefused({"geheim@example.org": (550, b"unknown user")})` wirft:

```
SUMMARY: {'sent': 0, 'given_up': 1, 'batches': 1, 'remaining': 0}
[WARNING] vote.services.mail: Eine Umfrage-Mail wurde dauerhaft abgelehnt und verworfen
```

Genau eine Zeile, **ohne** `exc_info`.

**Befund:** Der Kommentar über dieser Zeile sagt: „Der Text der Ausnahme kann die Adresse selbst
enthalten -- der landet über `logger.exception` im Log, das ist mit F8 bewertet und in Kauf
genommen." Im PERMANENT-Zweig steht aber `logger.warning`, nicht `logger.exception` -- der
Ausnahmetext landet **nirgends**. Der Kommentar beschreibt ein Risiko, das der Code nicht hat, und
verschweigt dabei die tatsächliche Folge: es ist auch **kein Grund** protokolliert, kein SMTP-Code,
kein Servertext. `logger.exception` gibt es nur bei `UnicodeEncodeError` und bei einem nicht
erreichbaren Server.

**Folge:** Zwei Dinge, beide klein. Betrieblich: verschwindet eine Einladung, steht im Journal
„eine Mail wurde abgelehnt" und sonst nichts -- kein 550 gegen 554, kein „unknown user" gegen
„message rejected". Wer wissen will, ob eine Adresse falsch war oder der Server zickt, kann es aus
dem Log nicht entscheiden. Und für die Bewertung von F8: die Notizen führen die Adresse-im-Log als
in Kauf genommenes Restrisiko, es gibt es an dieser Stelle gar nicht. Das ist Klasse **K6** --
plausibel begründet und trotzdem falsch, hier zugunsten der Anonymität.

**Vorschlag:** den SMTP-Code mitloggen (`_smtp_code(error)` ist bereits berechnet und ist eine Zahl,
keine Adresse) und den Kommentar auf das korrigieren, was passiert. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `6363cb1`**.

### R6-2 · Die Seite mit dem Token trägt kein `Cache-Control`

**Schwere:** Notiz
**Ort:** [../vote/views.py:79](../vote/views.py:79)
**Nachweis:** **gemessen**, Header von `GET /vote/<id>/`:

```
X-Frame-Options             : DENY
Referrer-Policy             : same-origin
X-Content-Type-Options      : nosniff
Content-Security-Policy     : -- fehlt --
Cross-Origin-Opener-Policy  : same-origin
Vary                        : Cookie
Cache-Control               : -- fehlt --
```

**Befund:** Die Seite zeigt den Wähler-Token in einem Eingabefeld. `Vary: Cookie` sagt einem Cache,
*wonach* er unterscheiden muss, aber nicht, dass er nicht speichern soll. Ohne `Cache-Control` gilt
für Zwischenspeicher die heuristische Regel, und für den Browser heißt es: die Seite darf auf Platte
liegen und aus der History wiederkommen. Der Proxy vor diesem Dienst cacht nicht
([deployment.md](deployment.md)), es ist also heute keine Lücke -- aber es ist die zweite Zusage
neben `@vary_on_cookie`, die niemand einlöst, wenn sich davor etwas ändert (vgl. **R10-1**).
CSP fehlt bekanntlich und gehört an den Proxy ([to-check.md](to-check.md) §B).

**Vorschlag:** `@never_cache` (oder `Cache-Control: private, no-store`) auf `poll()` und `manage()`.
Beides sind Seiten mit Token im Markup. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `5ddd491`**.

### R7-1 · Gedeckelt ist nur die Empfängerzahl — Textlängen, Choice-Zahl und Umfrage-Zahl nicht

**Schwere:** mittel
**Ort:** [../vote/forms.py:46](../vote/forms.py:46) (kein `max_length` an `description`/`choices`)
**Nachweis:** **gemessen**, ein unauthentifizierter POST auf `/vote/create`:

```
STATUS: 200
description gespeichert: 200000
choices gespeichert: 5000
poll-Seite mit 5000 Choices: status=200 queries=3 bytes=1362788
```

**Befund:** `VOTE_MAX_RECIPIENTS` deckelt die Zahl der Mails (B4/F5) -- das war die Frage, die F5
entschieden hat, und dort ging es um den SMTP-Missbrauch. Alles andere ist offen: die
Beschreibung ist ein `CharField` ohne `max_length` (200 000 Zeichen gespeichert), die Choice-Liste
ebenso (5 000 Choices angelegt, ein `INSERT` per `bulk_create`), und die Zahl der Umfragen ist
unbegrenzt. Die einzige wirksame Grenze ist Djangos `DATA_UPLOAD_MAX_MEMORY_SIZE` von 2,5 MB pro
Request, und die ist nirgends als Entscheidung notiert.

**Folge:** Zwei Wirkungen, beide ohne Authentifizierung erreichbar. **Platte:** ~2,5 MB je Request,
beliebig oft, auf derselben SQLite-Datei, die die Stimmen hält -- eine volle Platte auf
`/var/lib/demockrazy` nimmt die Abstimmung mit. **Bandbreite:** eine Umfrage mit 5 000 Choices
liefert 1,3 MB HTML pro Aufruf, aus 2,5 MB Eingabe wird also beliebig viel Ausgabe, und die Adresse
ist frei teilbar. Nebenbei gemessen: ein `multiple_choice` mit mehr als 1 000 Choices ist überhaupt
nicht abstimmbar, weil das Formular dann mehr Felder schickt, als
`DATA_UPLOAD_MAX_NUMBER_FIELDS` (1 000) erlaubt -- die Umfrage lässt sich anlegen und dann nicht
benutzen.

**Vorschlag:** `max_length` an `description` und `choices` (großzügig, etwa 10 000/20 000 Zeichen)
und eine Obergrenze für die Zahl der Choices, in derselben Größenordnung begründet wie der
Empfänger-Deckel. Ob die Umfrage-Zahl pro Zeit gedeckelt werden soll, ist eine Frage an den User --
F5 hat ein IP-Rate-Limit ausdrücklich abgelehnt, allerdings für den Mailversand.
Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `3e89f0c`**.

### R2-1 · Das Django-Admin ist erreichbar und legt Tokens und Stimmzahlen in fremde Hand

**Schwere:** **hoch** -- der User hat am 2026-08-04 bestätigt, dass es ein Staff-Konto gibt.
*(Stand 7.1: „hoch **wenn** …, sonst Notiz -- ungeklärt".)*
**Ort:** [../demockrazy/urls.py:10](../demockrazy/urls.py:10) ·
[../vote/admin.py:6](../vote/admin.py:6)
**Nachweis:** die Oberfläche ist **gemessen**, die Frage nach Konten ist **nicht messbar von hier**
(Arbeitsregel 10 -- die Prod-Datenbank liegt außerhalb dieses Repos):

```
/admin/                  -> 302 /admin/login/?next=/admin/
/admin/vote/token/       -> 302 …
/admin/login/            -> 200
Token-Liste zeigt token_string: False
Poll-Detail zeigt creator_token: True
Poll-Detail zeigt identifier: True
```

**Befund:** `django.contrib.admin` ist installiert und unter `/admin/` geroutet, und `vote/admin.py`
registriert `Poll`, `Choice` und `Token` ohne `readonly_fields`, ohne `list_display`, ohne
Einschränkung. Angemeldet als Staff kann man damit: jeden `creator_token` lesen (im Poll-Formular
sichtbar, gemessen), jeden `token_string` über die Detailseite lesen, **`Choice.votes` direkt
setzen** und Tokens löschen. Das ist nichts, was dieser Branch eingeführt hätte -- es steht so seit
2016 --, aber es ist der einzige Weg im ganzen Code, der die Stimmzahlen unmittelbar verändert, und
er ist im Review nicht auslassbar. Dazu: `/admin/login/` antwortet mit 200, ohne jede Drosselung von
Fehlversuchen.

**Folge:** Ein einziges Staff-Passwort ist gleichbedeutend mit „Ergebnisse frei editierbar" und
„alle Tokens lesbar". Ob es ein solches Konto gibt, entscheidet zwischen „hoch" und „Notiz".
Zwei Fragen an den User, sie gehören nach [to-check.md](to-check.md):
`SELECT username, is_staff, is_superuser, last_login FROM auth_user;` auf der Prod-Datenbank -- und
ob `/admin/` am Proxy überhaupt durchgelassen wird oder dort schon endet.

**Umgesetzt in 7.2 nach der Antwort des Users (`5adb612`)**, und zwar der beschneidende Weg statt
des entfernenden -- ein Konto existiert, also wird die Oberfläche gebraucht:

* `Choice.votes` ist `readonly`. Gemessen: ein POST mit `votes=9999` auf das Änderungsformular
  lässt die Zahl stehen, und ein neu angelegter Choice startet bei 0.
* `token_string` steht weder in der Liste noch im Formular -- ein Staff-Konto kann keinen
  Wähler-Token mehr lesen und damit nicht in fremdem Namen abstimmen.
* `creator_token` ist aus dem Poll-Formular entfernt (`exclude`, nicht `readonly` -- letzteres würde
  ihn weiterhin anzeigen), `identifier` ist `readonly`, weil Links darauf unterwegs sind.
* **Bewusst geblieben:** Löschen und `is_active` schalten. Das ist legitime Aufräumarbeit, und
  Djangos `LogEntry` hält fest, wer es getan hat.

Acht Tests in [../vote/tests/test_admin.py](../vote/tests/test_admin.py) fahren gegen die echte
Oberfläche mit `admin_client` (Superuser, also der stärkste Fall); mit der alten `admin.py`
zurückgespielt fallen sieben davon. Einer fiel dabei zuerst **nicht** -- der Test auf die
unveränderliche Kennung bestand auch vorher, weil der POST an einem anderen Pflichtfeld scheiterte.
Er prüft jetzt zusätzlich den Statuscode, sonst wäre er selbst ein K4-Fall.

**Der Teil, der in Django nicht lösbar war, ist entschieden:** `/admin/login/` hat keine Drosselung
von Fehlversuchen (gemessen: 200, kein Rate-Limit). Der User beschränkt `/admin/` am Proxy **auf das
Intranet** (2026-08-04) -- das macht ein Rate-Limit gegenstandslos, statt es nachzubauen, und erspart
eine zusätzliche Abhängigkeit. Die zwei Hälften greifen an verschiedenen Stellen und ersetzen sich
nicht: die Beschränkung nimmt die Angriffsfläche **von außen**, die `readonly`/`exclude`-Regeln
nehmen den Schaden **von innen** (Intranet, VPN, interne Maschine). Worauf beim Einbau zu achten ist,
steht in [to-check.md](to-check.md) A4 -- vor allem, dass die Regel an keiner Stelle steht, die ein
Test oder ein `check` sehen kann.

### R1-1 · Der Docstring von `OutgoingMail` verspricht mehr Unverknüpfbarkeit, als die Zeile hat

**Schwere:** niedrig (Dokumentation über Anonymität -- deshalb nicht „Notiz")
**Ort:** [../vote/models.py:126](../vote/models.py:126)
**Nachweis:** **gemessen**, Inhalt der zwei Zeilen einer frisch erstellten Umfrage:

```
recipient: wähler@example.org
subject  : [demockrazy] Deine Stimme für 'Geheim'
body     : … Dies ist dir über folgenden Link möglich:
           http://testserver/vote/3CP4p3gLFUW…JmjK/?token=6ijSgiRfSnAvVHNOZLL3…
Identifier der Umfrage: 3CP4p3gLFUW…JmjK
```

**Befund:** Der Docstring sagt: „**Keine Poll-Kennung.** Eine Zeile sagt für sich nicht, um welche
Abstimmung es geht." Für die *Spalten* stimmt das, für die Zeile nicht: der `body` enthält den
vollständigen Abstimmungslink, also den `identifier`, **und** den Token, **und** die
Empfängeradresse steht daneben. Eine Zeile sagt also genau: „diese Adresse ist zu dieser Umfrage
eingeladen und hat diesen Token." Der Betreff nennt zusätzlich den Titel.

Inhaltlich ist das **nicht neu und nicht falsch entschieden** -- plan.md §11.4 sagt es korrekt
(„die Paarung Adresse↔Token muss bis zur Zustellung existieren, weil der Mailtext den Token
enthält"), und die Einbuße ist bewertet: preisgegeben ist *wer eingeladen wurde*, nicht *wie jemand
gestimmt hat*. Falsch ist nur die Stelle, an der ein Leser zuerst nachsieht, nämlich am Modell.
Klasse **K6**: die Begründung („keine Poll-Kennung") trägt die Schlussfolgerung nicht.

**Nebenbei aus derselben Messung, und ebenfalls nicht dokumentiert:** die Zeile an den Ersteller
enthält den **`creator_token` im Klartext**. Er steht ohnehin in `vote_poll.creator_token`, es ist
also keine neue Preisgabe -- aber „eine zugestellte Zeile wird gelöscht, danach ist der Zustand
wieder der von vorher" gilt für den Management-Token nur, weil er auch vorher schon dastand.

**Vorschlag:** den Docstring auf „die *Spalten* tragen keine Poll-Kennung; der gerenderte Text
enthält Link und Token, siehe plan.md §11.4" korrigieren. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `4282901`**.

### R1-2 · Die Token-IDs stehen in Empfängerreihenfolge — wer die Liste hat, sieht, **wer** schon abgestimmt hat

**Schwere:** niedrig (die *Stimme* bleibt unverknüpfbar -- nur die Teilnahme ist es nicht)
**Ort:** [../vote/services/polls.py:38](../vote/services/polls.py:38) (`bulk_create` in
Listenreihenfolge) mit
[../vote/services/mail.py:277](../vote/services/mail.py:277) (`zip(voter_mails, tokens)`)
**Nachweis:** **gemessen**, fünf Empfänger über die echte create-View, dann zwei Stimmabgaben:

```
Adresse -> Token-pk: [('anna', 1), ('bert', 2), ('cara', 3), ('dora', 4), ('emil', 5)]
Token-pks aufsteigend in Eingabereihenfolge: True
nach Zustellung -- Adressen in der DB: 0 | Tokens: 5
bert (Position 2) und dora (Position 4) stimmen ab
verbleibende Token-pks: [1, 3, 5]
```

**Befund:** Die Tokens entstehen per `bulk_create` in genau der Reihenfolge, in der die Adressen
eingegeben wurden, und werden in derselben Reihenfolge zugeordnet -- Adresse *i* bekommt Token mit
der *i*-ten `id`. Nach dem Versand ist keine Adresse mehr in der Datenbank (gemessen), die
`id`-Reihenfolge bleibt aber. Wer die Empfängerliste in ihrer Eingabereihenfolge kennt **und** die
Datenbank lesen kann, liest an den verbliebenen `id`s ab, welche Personen noch nicht abgestimmt
haben.

Die zwei Voraussetzungen liegen heute bei verschiedenen Leuten (die Liste hat der Ersteller, die
Datenbank die Node), und **die Stimme selbst bleibt in jedem Fall unverknüpfbar**: eine Stimme ist
ein Zähler in `vote_choice`, ohne Zeile, ohne Zeitstempel, ohne Kennung. Deshalb niedrig und nicht
kritisch. Aufgeschrieben, weil R1 ausdrücklich fragt, was ein Leser der Datenbank *nach* dem Versand
noch erfährt -- und die Antwort ist nicht „nichts", sondern „die Teilnahme, falls er die Liste hat".
Das ist auch die Zusatzinformation, die F8 nicht bewertet hat: dort ging es um die Warteschlange,
also um die Zeit *während* des Versands.

**Vorschlag:** die Paarung mischen. Ein `random.SystemRandom().shuffle(tokens)` in
`poll_created_messages()` vor dem `zip` -- eine Zeile, kein Schemaeingriff, keine Verhaltensänderung
nach außen -- und die `id`-Reihenfolge sagt nichts mehr über die Listenreihenfolge.
Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `8c65cd3`**.

### R10-1 · `test_the_page_varies_on_cookie` besteht auch ohne `@vary_on_cookie` — ein Test, der nichts prüft

**Schwere:** mittel (kein Fehler im Produktivcode, aber eine falsche Zusage der Testsuite)
**Ort:** [../vote/tests/test_views.py:406](../vote/tests/test_views.py:406) gegen
[../vote/views.py:79](../vote/views.py:79)
**Nachweis:** **gemessen** per Mutation -- Dekorator entfernt, Suite gefahren:

```
UNBEMERKT  poll(): @vary_on_cookie entfernt -> 215 passed in 3.98s
```

**Befund:** Der Test prüft `"Cookie" in response.headers["Vary"]`. Diesen Header setzt aber bereits
die CSRF-Middleware, weil die Seite ein `{% csrf_token %}` enthält -- der Kommentar über dem
Dekorator weiß das sogar („Gemessen ist der Header heute schon da") und nennt es als Grund, ihn
*trotzdem* hinzuschreiben. Genau diese Absicht ist die einzige, die der Test nicht prüft: er kann
nicht fehlschlagen, solange irgendwer den Header setzt. Damit ist er die Klasse **K4** -- „Prüfung,
die nicht prüft" -- in reinster Form, und zwar dort, wo die Suite selbst behauptet, eine Zusage
abzusichern.

**Folge:** Fällt der Dekorator bei einem Umbau weg, bleibt die Suite grün. Verschwindet später auch
das `csrf_token` aus dem Template (etwa weil die Seite auf ein Django-Formular umgestellt wird),
fehlt `Vary: Cookie` **still** -- und ein gemeinsamer Cache darf dann die Seite eines Wählers samt
angezeigtem Token an den nächsten ausliefern. Heute steht kein solcher Cache davor (der Proxy
cacht nicht, siehe deployment.md), es ist also eine latente und keine aktuelle Lücke.

**Vorschlag:** die *Absicht* prüfen statt das Ergebnis: den Header an einer Response messen, die
ohne CSRF-Formular entsteht, oder direkt `poll.__wrapped__`/die Response einer Sicht ohne
`csrf_token` -- am billigsten wäre, den Test gegen die Response einer geschlossenen Umfrage
(Redirect, kein Formular) zu führen. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `eff438f`**.

### R10-2 · Die wichtigste Eigenschaft der Tokens — Unvorhersagbarkeit — ist von keinem Test gedeckt

**Schwere:** mittel
**Ort:** [../vote/models.py:16](../vote/models.py:16)
**Nachweis:** **gemessen** per Mutation -- `random.SystemRandom().choice` → `random.choice`:

```
UNBEMERKT  random statt SystemRandom -> 215 passed in 3.56s
```

**Befund:** Die Suite prüft Länge (128/256/64) und Zeichenvorrat der Tokens -- die
Token-Längen-Mutation wird sofort bemerkt (2 failed). Dass die Werte aus einem **kryptographisch
sicheren** Generator kommen, prüft nichts. `random.choice` benutzt den Mersenne Twister; wer ein
paar Tokens derselben Umfrage kennt (als eingeladener Wähler zum Beispiel), kann dessen Zustand
rekonstruieren und die übrigen Tokens **berechnen**.

**Folge:** Heute korrekt, aber ungesichert: ein `import random` an der falschen Stelle, eine
Umstellung „damit die Tests deterministisch werden" (ein sehr naheliegender Griff: `random.seed()`),
und aus dem einzigen Auth-Merkmal der Stimmabgabe wird ein berechenbarer Wert -- ohne dass ein Test
etwas sagt. Das ist die Fehlerklasse **K1** angewandt auf Zufall: es steht da, sieht richtig aus, und
niemand merkt, wenn es nichts mehr taugt.

**Vorschlag:** ein Test, der die Herkunft festnagelt statt die Form -- z. B. `rand_string` gegen
`random.SystemRandom` patchen und prüfen, dass es benutzt wird, oder (robuster gegen Umbauten)
prüfen, dass zwei Prozesse mit gleichem `random.seed()` **verschiedene** Tokens erzeugen.
Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `eff438f`**.

### R5-2 · Der Versandlauf hat keinen Wächter — die Schleife endet nur, weil jeder Zweig sie beendet

**Schwere:** Notiz
**Ort:** [../vote/services/mail.py:194](../vote/services/mail.py:194) (`while True:`)
**Nachweis:** **gemessen**, unbeabsichtigt: eine Mutation, die den `else`-Zweig für „Server nicht
erreichbar" entfernt (also eine Zeile, die weder löscht noch abbricht), hat die Testsuite in eine
**Endlosschleife** geschickt -- der Lauf hing nach 9,5 Minuten noch, ohne einen fehlschlagenden Test.
Erst eine Zeitgrenze von 90 s im Sondenskript machte es sichtbar.

**Befund:** `while True:` bricht ausschließlich ab, wenn `rows` leer ist oder `_send_batch()` `True`
liefert. Heute ist das vollständig: jeder der vier `_Outcome`-Fälle löscht die Zeile oder beendet den
Lauf. Es gibt aber keinen unabhängigen Wächter -- kein Deckel auf die Zahl der Batches, keine
Gesamtlaufzeit, keine Prüfung „diese Zeile lag im letzten Durchlauf auch schon vorn". Ein fünfter
Fall, der das Muster nicht einhält, dreht sich für immer, und weil der Command dabei die `flock`
hält, geht danach **überhaupt keine Mail mehr raus** -- dieselbe Endlage wie bei **R5-1**, nur ohne
Traceback im Journal.

**Folge:** heute kein Fehlverhalten. Aufgeschrieben, weil zwei der drei Wege in diese Endlage schon
belegt sind (R5-1 real, dieser durch Mutation) und weil der Lauf per Konstruktion minutenlang läuft
-- „hängt" sieht von außen aus wie „arbeitet noch".

**Vorschlag:** ein `max_batches` (oder eine Gesamtlaufzeitgrenze) als Notbremse, plus die
Beobachtung, dass sich die vorderste `pk` nicht bewegt. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `6363cb1`**.

### R8-1 · Gelöscht ist nicht rotiert: die sops-Geheimnisse des k8s-Deployments stehen weiter in der History

**Schwere:** Notiz (kein Klartext im Repo; die eigentliche Frage liegt außerhalb)
**Ort:** `k8s/environments/default/secrets.sops.yaml`, entfernt in `4e15012`, vorhanden in `master`
**Nachweis:** **gemessen** -- `git show master:k8s/environments/default/secrets.sops.yaml`:

```
secret_key:     ENC[AES256_GCM,…]
email_host:     ENC[AES256_GCM,…]
email_from:     ENC[AES256_GCM,…]
email_password: ENC[AES256_GCM,…]
sops: age1zd93w99zc846w379wftnxyquelfh4g45t2uejcn579n2hm257s3qy9u8sn + 3 PGP-Empfänger,
      created_at 2023-01-17
```

Und im Ist-Zustand des Branches: **kein Geheimnis**. Der Scan über alle `*.py`/`*.nix`/`*.toml`/
`*.yml`/`*.html` findet nur Prosa über `SECRET_KEY`, `import secrets`, Djangos
Passwort-Validatoren und den Testschlüssel `"test-only-not-a-secret"`.

**Befund:** Das Löschen des k8s-Verzeichnisses (richtig, F10) nimmt die Datei aus dem Arbeitsbaum,
nicht aus der Historie -- wer das Repo klont, hat die verschlüsselten Werte weiter, und wer einen der
vier Schlüssel hält, kann sie lesen. Verschlüsselt ist das keine Preisgabe. Die Frage, die es
aufwirft, ist eine andere: **ist `email_password` von 2023 noch ein gültiges Kennwort auf
`smtp.mayflower.de`?** Das ist derselbe Mailserver, über den Produktion heute verschickt. Wenn ja,
ist ein Kennwort im Umlauf, dessen Leserkreis niemand mehr prüft, und das Löschen der Datei hat
daran nichts geändert.

**Vorschlag:** Frage an den User, gehört nach [to-check.md](to-check.md): ob der SMTP-Account aus
dem k8s-Setup noch existiert und ob sein Kennwort seit 2023 rotiert wurde. Umschreiben der History
wäre unverhältnismäßig -- Rotation ist die richtige Antwort, falls sie nötig ist.
Nicht getan -- Regel 3 und Arbeitsregel 10.

### R10-3 · Drei weitere Defekte, die die Suite nicht bemerkt

**Schwere:** Notiz
**Nachweis:** **gemessen**, dieselbe Mutationssonde (26 Mutationen, 5 unbemerkt -- zwei davon sind
**R10-1** und **R10-2**):

```
UNBEMERKT  Batchgroesse 30 -> 1000                    -> 215 passed
UNBEMERKT  SQLite transaction_mode/journal_mode entfernt -> 215 passed  (siehe R9-2)
UNBEMERKT  Enthaltungen auch bei multiple_choice       -> 215 passed
```

**Befund:** (a) Die **Default-Werte** der Taktung (`30`/`2`) sind nirgends festgenagelt, obwohl sie
vom User vorgegeben sind und Produktion genau sie benutzt -- die Tests übergeben `batch_size`/`pause`
immer explizit. Dass *getaktet* wird, ist gut geprüft (die Mutation „Pause entfernt" fällt sofort
auf); *womit*, nicht. (b) Die Diagrammdaten für `multiple_choice` sind ungeprüft: die Zeile, die
Enthaltungen bewusst nur bei `simple_choice` anhängt (mit Begründung im Kommentar: bei
multiple_choice ist die Stimmensumme nicht die Wählerzahl), lässt sich abschalten, ohne dass ein Test
etwas sagt.

**Zum Gesamtbild:** 21 von 26 Mutationen wurden bemerkt, und die harten Zusagen sitzen fest --
Token-Löschung (7 Tests), Token-Länge, Adress-Dedup, Empfänger-Deckel, `flock`, `EMAIL_TIMEOUT`,
Mail-Autoescaping, Warteschlangen-Reihenfolge, `is_active`-Weichen, Choice-Reihenfolge, der
`identifier`-Converter, `zip(strict=True)`, der Management-Token-Vergleich und `atomic()` in `vote()`.
Das ist eine belastbare Suite; die fünf Lücken sind benannt, nicht der Normalfall.

**Vorschlag:** je ein Test für die zwei Punkte oben. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `eff438f`**.

### R10-4 · Das Mail-Double lehnt in der falschen Form ab — der Drosselungs-Zweig ist ungedeckt

*(Nachtrag, gefunden nach 7.2 bei der Frage, wo der handbetriebene Fake-Mailserver hingehört.)*

**Schwere:** Mittel
**Nachweis:** **gemessen**, dreifach.

(a) Was ein echter drosselnder Server durch Djangos SMTP-Backend auslöst — Sonde gegen `mailtrap`
mit `limit=1`:

```
message 1: accepted
message 2: smtplib.SMTPDataError
  smtp_code attr : 450
  recipients attr: <absent>
```

(b) Was die Suite erzeugt: `SMTPRecipientsRefused({recipient: (450, …)})`, von Hand gebaut
([test_mail_service.py:234](../vote/tests/test_mail_service.py:234)). `grep` über `vote/tests/` und
`demockrazy/`: **kein** Test konstruiert die `SMTPResponseException`-Form.

(c) Mutation von Zweig 1 in `_smtp_code` ([mail.py:106](../vote/services/mail.py:106)) auf
`code = None` → **242 passed** (`vote/tests`), kein Test sagt etwas.

**Befund:** `_smtp_code` deckt zwei Formen ab, weil smtplib zwei liefert: `SMTPResponseException`
trägt `smtp_code`, `SMTPRecipientsRefused` ein `(code, text)`-Paar je Empfänger. Der Code ist damit
richtig — aber `CountingBackend` liefert nur die **zweite**, und ein Server, der drosselt, antwortet
auf `DATA`, nicht auf `RCPT TO`, also kommt in Produktion die **erste** an. Geprüft wird der Zweig,
den Produktion *nicht* nimmt.

**Folge:** ohne Zweig 1 ist `code` gleich `None`, der `450` fällt durch auf `PERMANENT` und die
gedrosselte Einladung wird **verworfen statt wiederholt** — genau der Fehler, für dessen Verhinderung
die Batch-Mechanik existiert. Im Log stand bei der Mutation zweimal „SMTP-Code None dauerhaft
abgelehnt". Das ist keine hypothetische Lücke: es ist der Hauptfehlerfall des Versands (Ziel 2 des
Plans), und er war nur gegen eine selbstgebaute Ausnahme geprüft. **K4 in Reinform** — 261 grüne
Tests, und der Pfad, den der Mailserver von smtp.mayflower.de nimmt, war nicht darunter.

**Vorschlag:** der handbetriebene Fake-Server wird zum Gegenüber der Suite —
[vote/tests/mailtrap.py](../vote/tests/mailtrap.py), ein `ThreadingTCPServer` auf einem freien Port,
abhängigkeitsfrei (`smtpd` ist seit Python 3.12 aus der Standardbibliothek). Dazu **ein** Test, der
Djangos echtes `smtp.EmailBackend` dagegen laufen lässt und prüft, dass ein *echter* `450` als
`TRANSIENT` landet und die Zeile mit `attempts = 1` liegen bleibt. Gegenprobe: dieselbe Mutation
ergibt jetzt **1 failed, 242 passed**, und der Fehlschlag ist genau dieser Test. Der Handbetrieb
bleibt: `python3 -m vote.tests.mailtrap 30`. **Umgesetzt in `8b238f6`.**

### R11-1 · Eine `multiple_choice`-Stimme kostet ein `UPDATE` pro Choice — in der Transaktion, die alle Schreiber serialisiert

**Schwere:** Notiz
**Ort:** [../vote/views.py:194](../vote/views.py:194) (`record_multiple_choice`)
**Nachweis:** **gemessen**, Abfragen pro Request:

```
index 0 · poll 3 · manage 3 · results 3 · vote(simple) 8
vote(multiple, 10 Choices) 17
create(1 / 50 / 150 Empfänger) 8 / 8 / 8   ← konstant
create_poll(2 bzw. 200 Tokens): 5 Statements  ← die Zusage aus plan.md 3.5 hält
```

**Befund:** Alle Leseseiten sind konstant und klein, kein N+1 -- das ist der Hauptbefund und er ist
gut. Die eine Stelle, die mit der Datenmenge wächst, ist `record_multiple_choice`: ein `save()` je
mit „yes" beantworteter Choice, also ~N+7 Statements, und zwar **innerhalb** des `atomic()`-Blocks.
Auf SQLite mit `transaction_mode=IMMEDIATE` hält dieser Block die Schreibsperre für alle vier
uwsgi-Prozesse; bei den real vorkommenden Umfragen (wenige Choices) ist das nichts, bei einer
Umfrage mit 200 Choices sind es 200 Statements unter Sperre. Zusammen mit **R7-1** (Choice-Zahl
ungedeckelt) ist das der Weg, aus einer erlaubten Eingabe eine lange Schreibsperre zu machen.

**Vorschlag:** ein `Choice.objects.filter(pk__in=ja_ids).update(votes=F("votes") + 1)` statt der
Schleife -- ein Statement, gleiche Semantik. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `5ddd491`**.

### R9-3 · Der Rückwärtsweg der Migrations ist sauber — und wirft dabei die Warteschlange weg

**Schwere:** Notiz
**Ort:** [../vote/migrations/0004_outgoingmail.py](../vote/migrations/0004_outgoingmail.py)
**Nachweis:** **gemessen** auf einer frischen Datei-Datenbank:

```
Applying vote.0003… OK / Applying vote.0004… OK
Unapplying vote.0004_outgoingmail... OK
Unapplying vote.0003_model_constraints_and_choices... OK
EXIT: 0
wieder vorwärts: Applying 0003 … 0004 … OK
```

**Befund:** Der Rückwärtsweg `migrate vote 0002` läuft durch und der Vorwärtsweg danach wieder --
das ist die gute Nachricht und der Grund, das hier festzuhalten. Die stille Folge: `0004`
rückwärts ist ein `DROP TABLE vote_outgoingmail`. Wer nach einem Deploy zurückrollt, während
Einladungen in der Warteschlange liegen, **löscht sie**, und dann existieren Tokens, die niemand je
erfährt -- genau der Zustand, den der Docstring von `enqueue()` als Begründung dafür nennt, das
Einreihen in die Token-Transaktion zu legen. Es geht keine Stimme verloren, aber die betroffene
Umfrage schließt nie von selbst und der Ersteller muss sie von Hand beenden.

**Vorschlag:** kein Codeeingriff -- ein Satz in [to-check.md](to-check.md) beim Rollback-Verfahren:
vor einem Rückschritt hinter `0004` erst `send_pending_mails` leerlaufen lassen (oder
`SELECT count(*) FROM vote_outgoingmail` prüfen). Nicht getan -- Regel 3.

### R13-1 · Alle sechs Seiten heißen „Demockrazy" — der `{% block title %}` wird nie gefüllt

**Schwere:** niedrig
**Ort:** [../vote/templates/base.html:15](../vote/templates/base.html:15)
**Nachweis:** **gemessen** im Browser, Seite einer offenen Umfrage:
`document.title` → `"Demockrazy"`, und `grep -c "block title"` über alle sechs Vorlagen → **0**
Überschreibungen; der Block existiert nur in `base.html`.

**Befund:** Der Titelblock ist angelegt und wird von keiner Vorlage benutzt. Damit tragen
Erstellformular, Abstimmungsseite, Ergebnisseite, Bestätigungsseiten und die Manage-Seite denselben
Titel. WCAG 2.4.2 („Page Titled") verlangt einen Titel, der Thema oder Zweck der Seite beschreibt --
und praktisch relevanter: wer zwei Abstimmungen offen hat, unterscheidet die Tabs nicht, und der
Verlauf zeigt sechs identische Einträge. Der Umfragetitel steht in jedem Kontext bereits zur
Verfügung.

**Vorschlag:** `{% block title %}{{ poll.title }} – Demockrazy{% endblock %}` in den vier Vorlagen
mit Poll-Kontext, entsprechend in `index.html`/`create.html`. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `decb33b`**.

### R13-2 · Formularfehler sind schwarz auf weiß, während Abstimmungsfehler rot sind

**Schwere:** niedrig
**Ort:** [../vote/templates/vote/index.html:24](../vote/templates/vote/index.html:24) gegen
[../vote/templates/vote/poll.html:19](../vote/templates/vote/poll.html:19)
**Nachweis:** **gemessen** im Browser, echter POST mit ungültiger Adresse, dann berechnete Stile
der Fehlerliste:

```
ulColor: rgb(33, 37, 41)      # = body-Farbe
liFontSize: 16px
ulListStyle: disc
inputBorder: rgb(222, 226, 230)   # unverändert, kein is-invalid
bodyColor: rgb(33, 37, 41)
```

Die aria-Verdrahtung dagegen stimmt genau wie im Kommentar beschrieben -- nur die fehlerhaften
Felder tragen etwas:

```
creator_mail invalid=true describedby=creator_mail-errors
voter_mails  invalid=true describedby=voter_mails-errors
title/type/description/choices: invalid=null describedby=null
Eingaben bleiben erhalten (title, choices, beide Mailfelder)
```

**Befund:** Djangos `ul.errorlist` wird von Bootstrap 5 nicht gestylt (Bootstrap kennt
`.invalid-feedback`/`.is-invalid`), und `vote/static/css/main.css` enthält nur die
Navbar-Höhe. Eine Fehlermeldung im Erstellformular sieht also aus wie gewöhnlicher Text mit
Aufzählungspunkt, und das beanstandete Feld bleibt optisch unauffällig. Auf der Abstimmungsseite ist
derselbe Vorgang `alert alert-danger`, also rot mit `role="alert"`. Dieselbe Anwendung meldet
Fehler an zwei Stellen auf zwei Arten.
**Kein WCAG-Verstoß** (1.4.1 verlangt, sich *nicht allein* auf Farbe zu verlassen -- hier ist es
Text, das ist die konforme Richtung, und die aria-Verdrahtung ist korrekt). Es ist die
Bootstrap-3→5-Umstellung, die an dieser einen Stelle nicht mitgezogen ist: der Kommentar in
`index.html` spricht davon, dass die Meldung „optisch daneben" stehen soll, und beschreibt damit
eine Gestaltung, die es nicht gibt.

**Vorschlag:** `.errorlist` in `main.css` auf die Bootstrap-Fehlerfarbe legen (drei Zeilen, kein
Markup-Eingriff) oder die Felder bei Fehlern mit `is-invalid` markieren. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `decb33b`**.

### R15-1 · Die README beschreibt die Testsuite, wie sie vor 3.8 war

**Schwere:** niedrig
**Ort:** [../README.md:52](../README.md:52)
**Nachweis:** **gemessen** -- `grep -c xfail vote/tests/test_known_bugs.py` → **2 Treffer, beide im
Docstring** („Derzeit steht hier kein `xfail` mehr"), kein einziger Marker im Code.

**Befund:** Die README sagt: „`vote/tests/test_known_bugs.py` holds known defects written as the
behaviour that *should* hold, each marked `xfail(strict=True)`. Fixing one of them turns the suite
red." Seit 3.8 gilt das für keinen einzigen Test dieser Datei; alle sind gewöhnliche
Regressionstests, und die Datei sagt das selbst. Die Datei, die ein Neuer zuerst liest, beschreibt
damit einen Zustand, den es seit dem letzten Bugfix nicht mehr gibt -- und weckt die Erwartung, ein
grüner Lauf enthalte noch bekannte offene Defekte.

**Zwei kleinere Ungenauigkeiten in derselben Datei**, aus demselben Anlass mitgeprüft:
die Aufzählung der `DEMOCKRAZY_*`-Variablen (README „Configuration") nennt sechs und **lässt vier
weg**, die `settings.py` liest: `DEMOCKRAZY_MAIL_TIMEOUT`, `DEMOCKRAZY_MAX_RECIPIENTS`,
`DEMOCKRAZY_MAIL_BATCH_SIZE`, `DEMOCKRAZY_MAIL_BATCH_PAUSE` -- also gerade die zwei Schrauben, an
denen laut Notizen im Störungsfall gedreht wird. Und der Satz „A queue row … names no poll" hat
dasselbe Problem wie **R1-1**: der `body` enthält den Abstimmungslink.

**Vorschlag:** die drei Stellen nachziehen. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `4282901`**.

### R14-1 · Die Ergebnisseite einer Alt-Umfrage zeigt „Total Voters: None"

**Schwere:** niedrig
**Ort:** [../vote/templates/vote/results.html:26](../vote/templates/vote/results.html:26)
**Nachweis:** **gemessen**, Umfrage mit `num_tokens=None` angelegt, `GET …/results`:

```
STATUS: 200
CONTEXT: 'Total Voters</td>\n        <td>None</td>'
```

**Befund:** `Poll.num_tokens` ist `null=True`, und `get_amount_used_unused()` behandelt den Fall
ausdrücklich („Alt-Umfragen ohne Empfängerliste"). Das Template umgeht diese Sorgfalt und gibt das
Rohfeld aus, also den String `None`, obwohl der berechnete Wert (`amount_tokens_total`) im selben
Kontext liegt und in `token_state.html` direkt darüber korrekt angezeigt wird.

**Folge:** Nur Kosmetik, aber sichtbar für den Bestand -- Prod hat Umfragen von vor 2016. Zwei
Zahlen auf einer Seite, die dasselbe meinen und verschieden aussehen.

**Vorschlag:** `{{ amount_tokens_total }}` statt `{{ poll.num_tokens }}`. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `decb33b`**.

### R14-2 · Vier Kommentare beschreiben einen Zustand, den der Code hinter sich hat

**Schwere:** niedrig
**Nachweis:** **gemessen**, jede Behauptung gegen den Code geprüft:

| Ort | Behauptung | Gemessener Stand |
|---|---|---|
| [../vote/services/mail.py:165](../vote/services/mail.py:165) | „Gibt eine Zusammenfassung als dict zurück (`sent`, `given_up`, `deferred`, `batches`)" | `{'sent': 0, 'given_up': 1, 'batches': 1, 'remaining': 0}` -- **`deferred` gibt es nicht**, `remaining` ist nicht dokumentiert (und ist der Schlüssel, den der Command ausgibt) |
| [../vote/services/mail.py:273](../vote/services/mail.py:273) | `poll_created_messages`: „damit `deliver()` ohne Datenbankzugriff auskommt und als `on_commit`-Callback laufen kann" | `deliver()` ist mit §11.7 entfallen (der Modul-Docstring 15 Zeilen höher sagt das), ein `on_commit` gibt es nicht mehr |
| [../vote/templates/vote/index.html:4](../vote/templates/vote/index.html:4) | „Das Markup bleibt absichtlich handgeschrieben (Bootstrap 3, wird in Plan 4.1 ersetzt)" | Bootstrap **5**: 6× `mb-3`, 6× `form-label`, 5× `form-control`, 1× `form-select`, **0** BS3-Klassen. 4.1 ist erledigt |
| [../vote/static/chartjs-4.5.1/PROVENANCE.md](../vote/static/chartjs-4.5.1/PROVENANCE.md) | Verzeichnisname „steht in `vote/templates/vote/base.html` bzw. `results.html`" | Diesen Pfad gibt es nicht (`vote/templates/base.html`), und Chart.js steht **nur** in `results.html` |

**Befund/Folge:** Kein Fehlverhalten, aber jede dieser Stellen kostet den nächsten Leser eine
Fehlsuche -- die `deferred`-Zeile am meisten, weil sie einen Schlüssel verspricht, auf den man Code
schreiben kann. Sie ist zugleich das Nachbeben von **K5**: der `deferred`-Zähler war der
Buchhaltungsfehler des ersten Entwurfs, er wurde aus dem Code entfernt und blieb im Docstring stehen.
Die `PROVENANCE`-Zeile ist die einzige, die eine Anleitung falsch macht (sie sagt, wo beim nächsten
Upgrade zu suchen ist).

**Vorschlag:** vier Textkorrekturen, kein Codeeingriff. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `4282901`**.

### R14-3 · `get_amount_used_unused()` wird an fünf Stellen aufgerufen, viermal mit demselben Dreizeiler

**Schwere:** Notiz
**Ort:** [../vote/views.py:100](../vote/views.py:100), :173, :254, :272 (und :202 mit `_, x, _`)
**Nachweis:** **gemessen**, `grep -n "get_amount_used_unused()" vote/*.py` → 5 Treffer in `views.py`,
vier davon in derselben Form mit anschließend drei identischen Kontextschlüsseln.

**Befund:** Vier Views bauen denselben Kontextausschnitt (`amount_redeemed_tokens`,
`amount_remaining_tokens`, `amount_tokens_total`) für dasselbe Include (`token_state.html`) aus
demselben Aufruf. Das ist keine falsche Logik, aber der Ort, an dem eine Änderung an der
Token-Statistik viermal nachgezogen werden muss -- die Sorte Duplikat, die still auseinanderläuft.

**Vorschlag:** entweder ein `token_state_context(poll)`-Helfer, oder (näher an Django)
ein `inclusion_tag` für `token_state.html`, das sich seine Zahlen selbst holt. Während des Reviews nicht getan (Regel 3), **umgesetzt in 7.2: `9bf0fc7`**.

---

Format je Befund:

```
### Rn-1 · Kurztitel
**Schwere:** kritisch | hoch | mittel | niedrig | Notiz
**Ort:** pfad/datei.py:42
**Nachweis:** gemessen (Befehl/Testfall/Zahl) — oder ausdrücklich „gelesen, nicht gemessen"
**Befund:** was falsch ist.
**Folge:** was im Betrieb passiert.
**Vorschlag:** was ich tun würde. Nicht getan — Regel 3.
```

Schweregrade sind für *dieses* Projekt definiert, nicht generisch:

- **kritisch** — verletzt die Anonymität, verliert oder verfälscht Stimmen, oder öffnet die
  Stimmabgabe für Unbefugte.
- **hoch** — Ausfall im Betrieb, Datenleck ohne Stimmbezug, oder etwas, das beim Deploy still bricht.
- **mittel** — falsches Verhalten in einem Randfall, das auffällt und nichts zerstört.
- **niedrig** — Kosmetik mit Folgen, z. B. irreführende Meldung.
- **Notiz** — kein Fehler, aber jemand wird darüber stolpern.

## 6. Negativraum — was geprüft wurde, ohne Befund

Ein Absatz je Kriterium: **wie** geprüft wurde. Ohne diesen Abschnitt ist „keine Befunde" nicht von
„nicht hingesehen" zu unterscheiden.

**R1 Anonymität.** Der Weg von der Stimme zum Wähler wurde von beiden Enden aus gesucht. Eine Stimme
ist ein Zähler in `vote_choice` -- **keine Zeile pro Stimme, kein Zeitstempel, keine Kennung**, also
gibt es nichts, woran eine Verknüpfung hängen könnte; das ist gelesen und an der Migration `0001`
gegengeprüft. Gemessen: nach einer vollständigen Stimmabgabe über HTTP stehen **0 Zeilen in
`django_session`** (nichts schreibt in die Session, obwohl `SessionMiddleware` läuft), und der Client
trägt genau zwei Cookies (`csrftoken`, `vote_token`). `document.cookie` im Browser zeigt
`vote_token` **nicht** -- `httponly` wirkt. Der Versender loggt weder Adresse noch Umfragekennung
(gemessen, siehe R6-1, dort sogar strenger als dokumentiert). Was übrig bleibt, steht als **R1-1**
(Warteschlange während des Versands, F8-Entscheidung) und **R1-2** (Reihenfolge der Token-IDs).
Nicht geprüft, weil außerhalb: Backups (borg) und was ein Angreifer aus einem WAL-Restbestand liest.

**R2 Auth/Autorisierung.** Token-Erzeugung gelesen (`SystemRandom`, 64/128/256 Zeichen aus 62er
Alphabet -- Entropie weit jenseits jedes Brute-Force; der fehlende *Test* dafür ist **R10-2**).
Verbrauch: `token.delete()`, geprüft an 7 Tests, die bei entfernter Löschung sofort fehlschlagen
(Mutation). Der Management-Token wird mit `==` verglichen, also nicht in konstanter Zeit -- bei 256
Zeichen aus einem CSPRNG **kein praktischer Angriff** (gelesen, nicht gemessen; ein Zeitkanal über
HTTP trägt kein Präfixwissen dieser Größe). Ohne Token erreichbar sind: Erstellformular (F5
entschieden), `/healthz` (gemessen: 200/`ok`, 503 ohne Pfadangabe im Body, POST → 405) und die
Manage-Seite ohne POST -- alle drei bewusst. Der Cookie-Pfad ist gegen die echten `reverse()`-Routen
geprüft (bestehender Test) und die Isolation zweier Umfragen über das `path`-Attribut. Befund:
**R2-1** (Admin).

**R3 Eingabeprüfung/Injection.** Kein rohes SQL außer `SELECT 1` in `/healthz`; alle Lookups laufen
über das ORM mit Parametern. Autoescaping: im Browser gemessen, dass ein Titel
`Bier & Brezn <script>` als `&lt;script&gt;` ankommt, **ein** `script`-Element auf der Seite bleibt
(Bootstrap) und die Konsole leer ist -- die B17-Falle ist zu. `json_script` liefert
`{"name": "Ja & so"}` und das Diagramm zeigt `Ja & so` (also weder doppelt escaped noch
interpoliert, B10 hält). Die Mail-Templates haben Autoescaping bewusst aus; die Mutation „wieder an"
fällt sofort auf. Header-Injection über den Mail-Betreff ist **nicht möglich** (Django blockt, siehe
R5-1 -- das Problem dort ist die ungefangene Ausnahme, nicht die Injection). Redirect-Ziele werden
ausschließlich per `reverse()` gebaut, es gibt keinen Parameter, der in ein `Location` fließt -- also
kein offener Redirect. Der eigene URL-Converter ist auf `[a-zA-Z0-9]+` beschränkt und die Lockerung
auf Slug-Zeichen fällt in der Suite auf (Mutation). Befund: **R3-1** (der Query-Parameter, der ins
Cookie geht).

**R4 Nebenläufigkeit/Datenintegrität.** Mit echten Threads gegen eine Datei-Datenbank mit der
Prod-Härtung gemessen, nicht überlegt: 100 Runden zwei gleichzeitige Stimmabgaben → **R4-1**. Die
zwei `UniqueConstraint`s sind vorhanden und in `0003` angewendet (gemessen: `migrate` vorwärts und
rückwärts). `F()`-Ausdrücke werden für die Zähler benutzt, das Lost-Update *innerhalb* einer Stimme
gibt es also nicht -- das Problem in R4-1 ist die fehlende Bedingung, nicht die Arithmetik.
`atomic()`-Grenzen: in `vote()` vorhanden und wirksam (Mutation fällt auf), in `create_poll()`
ebenso, und **kein `sleep` innerhalb einer Transaktion** im Versender (gelesen; die Messung dazu
steht in plan.md §11.7). Die `flock` ist getestet (Mutation „entfernt" fällt auf), und ein zweiter
Aufruf während eines Laufs endet mit Rückgabecode 0 und einem Satz -- kann also weder hängen noch als
Fehlschlag im Journal stehen; einen Weg, in dem die Sperre *hängenbleibt*, habe ich nur als **R5-2**
konstruieren können.

**R5 Fehlerbehandlung.** Jedes `except` gelesen und den Weg dahinter gegangen: `vote()` fängt
`Token.DoesNotExist`, `KeyError`, `Choice.DoesNotExist`, `ValueError` und liefert jeweils eine
200-Seite mit Meldung (die vier Wege sind bestehende Tests). `_send_one()` unterscheidet vier
Ausgänge, und die Unterscheidung 4xx/5xx/unerreichbar ist an Tests gebunden, die bei Mutation
fehlschlagen. `healthz` fängt jede Exception und antwortet 503 ohne Details. Zwei Löcher gefunden:
**R5-1** (`BadHeaderError` ist eine `ValueError`-Unterklasse und wird nicht gefangen) und **R3-1**
(`CookieError`). Kein Pfad in einen 500 gefunden bei: fehlenden POST-Feldern, unbekanntem Token,
Token einer anderen Umfrage, nicht-numerischem `choice`, GET auf `/vote/create`, POST ohne
Token-Feld auf `manage`, unbekannter Umfragekennung (404). Plattenplatz und SMTP-Ausfall: gelesen
(die Zeile bleibt liegen, kein `attempts`-Verbrauch), Plattenvolllauf nicht gemessen.

**R6 Informationslecks.** Header gemessen: `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`,
`X-Content-Type-Options: nosniff`, `Cross-Origin-Opener-Policy: same-origin`, `Vary: Cookie`.
Fehlerseiten: `DEBUG=False` ist Default, Prod setzt es explizit (F14). Der 503-Body von `/healthz`
ist `database unavailable\n` -- **ohne** Pfad, obwohl der Exception-Text ihn enthält (der geht ins
Log). Die Logzeilen des Versenders enthalten keine Adresse (gemessen). Das `mails_pending`-Bit ist
global und verrät damit, dass *irgendeine* Umfrage gerade verschickt -- bewusst so (§11.7 Punkt 7),
und ohne Poll-Bezug nicht mehr als „der Dienst wird benutzt". Befunde: **R6-1**, **R6-2**.

**R7 Missbrauch/DoS.** Gemessen, was ein unauthentifizierter POST erreicht: 200 000 Zeichen
Beschreibung, 5 000 Choices, 1,3 MB Antwort → **R7-1**. Der Empfänger-Deckel greift **nach** der
Deduplizierung (bestehender Test, Mutation fällt auf). `EMAIL_TIMEOUT` steht auf 10 s und ist
getestet (Mutation auf `None` fällt auf). Laufzeit des Versenders: durch `flock` serialisiert, und
ein langer Lauf kostet die Stimmabgabe 7--9 ms (Messung in plan.md §11.7, hier nicht wiederholt).
Kein Rate-Limit auf `/admin/login/` (siehe R2-1). Nicht gemessen: ob viele parallele
Umfrage-Erstellungen die SQLite-Schreibsperre praktisch blockieren.

**R8 Geheimnisse.** Der Ist-Zustand enthält **kein** Geheimnis: der Scan über alle
`*.py`/`*.nix`/`*.toml`/`*.yml`/`*.html` findet nur Prosa über `SECRET_KEY`, `import secrets`,
Djangos Passwort-Validatoren und `"test-only-not-a-secret"` in den Testsettings. Der `SECRET_KEY`
fällt ohne Umgebungsvariable auf `secrets.token_urlsafe(64)` pro Prozess zurück -- kein Schlüssel im
Repo, und bewusst kein Raise (Falle 1). Cookie-Flags: `httponly` und `samesite=Lax` gemessen,
`secure` folgt `SESSION_COOKIE_SECURE` (Test prüft beide Richtungen). Im Branch-Diff kam **keine**
Geheimnis-Zeile hinzu außer dem auskommentierten `# EMAIL_HOST_PASSWORD = "derp"` von 2016, das aus
`settings.py` mitgewandert ist. Befund: **R8-1** (History).

**R9 Migrations & Deploy-Sicherheit.** `0001`--`0004` gelesen und gegen die Beschreibung in
`phase-2-migrations.md` gehalten; vorwärts *und* rückwärts auf einer frischen Datei gefahren
(gemessen, beides fehlerfrei, danach wieder vorwärts). `0004` ist rein additiv (`CreateModel`), also
kein Tabellen-Neubau. Die K1-Frage („welche Einstellung geht über `demockrazy_config` still
verloren") ist der Kern von **R9-1**/**R9-2**; zusätzlich als offene Frage: **F17** ist weiter offen,
und die vier Mail-Text-Settings sind aus `settings.py` verschwunden -- ein Override im Modul wäre
still wirkungslos. Nicht prüfbar von hier: das Modul selbst, der `preStart`, die Prod-Node
(Arbeitsregel 10).

**R10 Testabdeckung/Testqualität.** Nicht gelesen, sondern **kaputtgemacht**: 26 Mutationen an
Produktivcode und Settings, jede einzeln, Suite je Mutation gefahren. **21 wurden bemerkt, 5 nicht**
(→ R10-1, R10-2, R10-3, R9-2). Das ist der belastbare Teil dieses Kriteriums, und er sagt: die Suite
prüft Wirkung, nicht Implementierung, und sie sitzt fest an den Zusagen, auf die es ankommt.
`create_poll` geht über die echte View und liest die Tokens **aus den Mails**, nicht aus der
Datenbank -- ein Test kann also nicht dadurch grün sein, dass er dieselbe Quelle zweimal befragt.
Nicht geprüft: eine Zeilenabdeckung (kein `coverage` im Flake) -- die wäre hier auch das schwächere
Werkzeug.

**Korrektur (Nachtrag).** Dieser Absatz sagte „die Fixtures sind ehrlich" und stützte das auf
`create_poll`. Für ein Fixture war es falsch: `CountingBackend` stellt die SMTP-Ablehnung in einer
Form nach, die ein echter Server so nicht liefert (**R10-4**). Die Mutationssonde konnte das nicht
finden, weil sie den Produktivcode verändert und die Doubles unangetastet lässt -- eine Mutation, die
den ungedeckten Zweig trifft, sieht aus wie „21 von 26 bemerkt", und der Zweig zählt nirgends mit.
**Die Lehre für das nächste Review:** ein Double gegen das echte Gegenüber halten, nicht nur den Code
gegen das Double. Gefunden hat es die Frage, wo ein handbetriebener Fake-Server hingehört -- nicht die
Sonde.

**R11 Performance.** Abfragen pro Request gemessen: `index` 0, `poll` 3, `manage` 3, `results` 3,
`vote(simple)` 8. **Kein N+1**: `results()` materialisiert `choices` einmal für Tabelle und
Diagramm, und die Umfrage-Erstellung ist bei 1, 50 und 150 Empfängern **konstant 8 Abfragen**;
`create_poll()` selbst kostet bei 2 wie bei 200 Tokens **5 Statements** (Savepoint, drei INSERTs,
Release) -- die Zusage aus plan.md 3.5 hält, gemessen. Die Warteschlangen-Abfrage ist ein
`order_by("pk")[:batch_size]`, also indexgestützt und begrenzt. Einzige wachsende Stelle:
**R11-1**.

**R12 Lieferkette/Lizenzen.** Die drei vendorten Dateien gegen `PROVENANCE.md` nachgerechnet, alle
drei **byteidentisch zur dokumentierten Summe nach dem Strippen**:
`bootstrap.min.css` `8f8173cb…e4ff`, `bootstrap.bundle.min.js` `c6f67021…c386a`,
`chart.umd.min.js` `84d0e233…cf4b`. Die dokumentierte Änderung (letzte Zeile mit
`sourceMappingURL` entfernt) ist die einzige; das Dateiende von `chart.umd.min.js` endet auf
`window.Chart=Tn),Tn}));` ohne Map-Verweis. Lizenzen: Bootstrap MIT, Chart.js MIT mit beiliegender
`LICENSE.md`, Repo MIT -- durchgehend. nixpkgs ist über `flake.lock` auf
`mayflower/nixpkgs` rev `cd21fa49…` gepinnt (ein Input, keine transitiven). Die zwei CI-Actions
sind **gegen die GitHub-API nachgeprüft** und existieren wie in plan.md behauptet:
`actions/checkout` hat `v7.0.1`/`v7`, `cachix/install-nix-action` hat `v31.11.0`. Sie hängen an
beweglichen Major-Tags statt an einem SHA -- bei `permissions: contents: read` und ohne Secrets im
Workflow ist die Reichweite klein, deshalb kein eigener Befund, aber es ist der Unterschied zwischen
„gepinnt" und „benannt".

**R13 Barrierefreiheit.** Im Browser gemessen, nicht am Markup geraten: `lang="en"`, genau eine
`h1`, `main`-Landmark vorhanden, `fieldset`/`legend` („Your choice") um die Radiogruppe, jedes
`label` hat ein `for`, das auf ein existierendes `id` zeigt (`choice1..3`, `token`), und die
Tabreihenfolge folgt der Leserichtung. Die aria-Verdrahtung der Fehlerfälle stimmt genau wie
dokumentiert: `aria-invalid`/`aria-describedby` erscheinen **nur** an den beanstandeten Feldern, und
die Eingaben stehen zurück im Formular. Kontrast der Badges gemessen: Weiß auf `#6c757d` = **4,70:1**,
also über AA (4,5). Das Diagramm trägt `role="img"` und ein `aria-label`, und die Tabelle mit
denselben Zahlen steht davor. Befunde: **R13-1**, **R13-2**. Nicht geprüft: Screenreader-Durchlauf,
Zoom auf 200 %, Dark-Mode.

**R14 Lesbarkeit/Wartbarkeit.** Namen und Aufbau gelesen; die Schichtung (View → Service → Modell)
ist konsequent, `views.py` enthält nur noch Ablaufsteuerung. Toter Code: keiner gefunden -- `ruff`
mit `F` würde ihn melden, und die drei `per-file-ignores` sind begründet und nachgeprüft (F403 für
den Sternchen-Import, E501 für die Mail-Wortlaute, RUF012 für `Meta.constraints`). **Kommentarlänge**
(Regel 11): die neuen Stellen halten sich an ein bis zwei Zeilen, die langen Docstrings in
`services/mail.py` und `models.py` sind die bekannten Altlasten aus früheren Commits -- Kürzen ist
angeboten, nicht beauftragt. Befunde: **R14-1**, **R14-2** (irreführende Kommentare), **R14-3**
(Duplikat). Kleinigkeit ohne eigene Nummer: `vote/admin.py` trägt noch das Gerüst-Kommentar
„# Register your models here." und `settings.py` zwei auskommentierte `EMAIL_HOST_*`-Zeilen von 2016.

**R15 Dokumentation.** README, `handover.md` und die geprüften Teile von `plan.md` gegen den Code
gehalten. Bestätigt: die Sollwerte in handover §4 (**215 passed** gemessen), „konstant 5 Statements"
(gemessen), „164 von 200" bzw. „36 of 200 succeed" (konsistent zwischen README, `checks.py` und
Notizen), die `PROVENANCE`-Summen (gemessen), die CI-Action-Versionen (gemessen), „kein `xfail` mehr"
(gemessen -- aber die README sagt das Gegenteil, **R15-1**). Befunde: **R15-1**, **R14-2**.
Nicht systematisch geprüft: `deployment.md`, `phase-0-baseline.md`, `phase-2-migrations.md` und
`to-check.md` -- sie beschreiben überwiegend Dinge außerhalb dieses Repos, die ich nicht messen kann.

## 7. Was noch nicht geprüft ist

Damit der Stand nicht mit „fertig" verwechselt wird. In dieser Reihenfolge würde ich weitermachen:

1. **Die Testsuite als Text** -- 2 213 Zeilen. Gelesen habe ich `conftest.py` vollständig und
   `test_views.py` in Teilen; das Urteil in R10 stützt sich auf die **Mutationssonde**, nicht auf
   eine Lektüre aller 215 Tests. Ein Test, der etwas Falsches *behauptet* (nicht: nichts prüft),
   fällt nur beim Lesen auf -- R10-1 wurde durch die Mutation gefunden, ein zweiter dieser Art wäre
   nicht überraschend.
2. **Der Branch als Verlauf** -- 80 Commits. Bisher habe ich den **Ist-Zustand** und den Gesamtdiff
   geprüft. Was unterwegs eingeschleppt und wieder entfernt wurde (§1 nennt das ausdrücklich als
   Grund, beides zu prüfen), habe ich noch nicht Commit für Commit angesehen.
3. **`plan.md` vollständig** (1 295 Zeilen) sowie `deployment.md`, `phase-0-baseline.md`,
   `phase-2-migrations.md`, `to-check.md` gegen den Code.
4. **Die vendorten Bundles inhaltlich** -- geprüft ist die Summe gegen `PROVENANCE.md`, **nicht**
   die Summe gegen den Upstream (dafür müsste ich die Archive ziehen).
5. **Die Mail-Templates byteweise** gegen die früheren `VOTE_*`-Settings -- `test_mail_service.py`
   behauptet das, und ich habe die Behauptung nicht gegen `master` nachgerechnet.
6. **Die übrigen Doubles gegen ihr echtes Gegenüber.** **R10-4** hat das für SMTP nachgeholt, und der
   Befund war ein echter. Dieselbe Frage ist für die anderen Doubles offen und von der
   Mutationssonde grundsätzlich nicht zu beantworten: `recorded_sleep` nimmt Pausen auf, statt zu
   warten, und `locmem` überspringt die Verbindung ganz. (Der `flock`-Test ist **nicht** in dieser
   Liste: er sperrt wirklich, per `fcntl` auf einem zweiten Deskriptor, und die Begründung steht im
   Docstring.)
7. **Nicht messbar von hier** (Arbeitsregel 10, gehört nach [to-check.md](to-check.md)): NixOS-Modul,
   Colmena-Repo, Proxy-vhost, Prod-Node, Backups -- und die drei Fragen, die dieser Lauf neu
   aufwirft: existiert in Prod ein Staff-Account (R2-1), ist das SMTP-Kennwort von 2023 noch gültig
   (R8-1), und liegt in der Prod-Warteschlange gerade etwas, das ein Rollback vernichten würde
   (R9-3).

---

## 8. Zweiter Lauf — die sechs Commits nach 7.2

**Umfang:** `3418317..565abc1` (R10-4, die Sprachumstellung, README, Notizen) plus der Ist-Zustand.
Angelegt 2026-08-14, nach dem Push. Dieselben Regeln wie §2, dieselben Fehlerklassen wie §3 --
der Grund für diesen Lauf ist, dass zwischen den beiden Läufen etwa 1 200 Zeilen Prosa und eine
neue Datei dazugekommen sind, und dass ich beides selbst geschrieben habe (Regel 1).

### R15-2 · Die Anleitung zum Fake-Mailserver funktioniert nicht, wenn man ihr folgt

**Schwere:** Mittel
**Nachweis:** **gemessen**, drei Läufe gegen *einen* Trap-Prozess (`limit=5`, 8 Zeilen in der
Warteschlange, `--pause 0`):

```
--- run 1 ---   5 verschickt, 0 aufgegeben, 3 warten noch (1 Batches).
--- run 2 ---   0 verschickt, 0 aufgegeben, 3 warten noch (1 Batches).
--- run 3 ---   0 verschickt, 0 aufgegeben, 3 warten noch (1 Batches).
```

Und zehn Läufe gegen einen Trap mit `limit=1` bei zwei Zeilen:

```
run  1: 1 verschickt, 0 aufgegeben, 1 warten noch (1 Batches).
run  2..9: 0 verschickt, 0 aufgegeben, 1 warten noch (1 Batches).
run 10: Eine Umfrage-Mail wurde 10 mal vorläufig abgelehnt und aufgegeben
        0 verschickt, 1 aufgegeben, 0 warten noch (1 Batches).
queue at the end: []
```

Gegenprobe, dass der Neustart der Reset ist: dieselbe Warteschlange gegen einen **frisch gestarteten**
Trap → `3 verschickt, 0 aufgegeben, 0 warten noch`.

**Befund:** [README](../README.md) und [handover.md](handover.md) §7 sagen beide: „Queue more than 30
invitations and run the command twice: the first run stops at the `450`, the second one drains the
rest." Das gilt nicht. `MailTrap` zählt in `self.accepted`/`self.throttled` über die **Lebensdauer des
Prozesses** und hat kein Zeitfenster -- anders als der echte Mailserver, dessen Drosselung sich nach
dem Fenster zurücksetzt. Der zweite Lauf trifft denselben Zähler und schickt nichts.

Der eigentliche Ablauf meiner Demo war ein anderer: ich habe den Trap zwischen den Läufen **neu
gestartet**. Genau der Schritt fehlt in der Anleitung, und weil er in der Messung nicht auffiel,
ist er auch in der Prosa verlorengegangen -- **K6**, plausibel begründet und trotzdem falsch.

**Folge:** wer der Anleitung folgt, sieht ab Lauf 2 `0 verschickt` und ab Lauf 10, dass eine
Einladung **weggeworfen** wird. Beides ist korrektes Verhalten des Versenders gegenüber einem Server,
der dauerhaft `450` sagt -- aber die Anleitung stellt es als Vorführung des *Normalfalls* dar. Sie
lehrt damit das Gegenteil dessen, was sie zeigen soll: nicht „ein `450` kostet keine Mail", sondern
„der Versender verliert Mails". Das ist die gefährlichere Richtung, weil das Werkzeug für genau diese
Frage gebaut wurde.

**Vorschlag:** zwei Möglichkeiten, und die zweite ist die bessere.
(a) Die Anleitung um den Neustart ergänzen -- eine Zeile, aber sie verlangt vom Leser, den Unterschied
zum echten Server zu kennen.
(b) `MailTrap` ein **Zeitfenster** geben, wie Postfix es hat: ein `window`-Parameter, nach dessen
Ablauf der Zähler zurückgesetzt wird. Dann stimmt die Anleitung wörtlich, das Double verhält sich wie
sein Gegenüber, und die Lehre aus R10-4 („ein Double gegen das echte Gegenüber halten") wird auf das
Double selbst angewandt. Der Trap braucht dafür eine Zeitquelle -- im Test bleibt `limit` ohne Fenster
die richtige Wahl, weil ein Test nicht auf Uhrzeit warten darf.
Während des Reviews nicht getan (Regel 3).

### R10-5 · Das neue Double ist nachsichtiger als sein Gegenüber — ungeprüft in drei Punkten

**Schwere:** Notiz
**Nachweis:** **gemessen**, drei Sonden gegen `vote.tests.mailtrap`.

(a) Ein Client, der mitten in `DATA` abbricht:

```
  accepted=['d@e.f'] throttled=[]      # die halbe Nachricht zählt als zugestellt
BrokenPipeError: [Errno 32] Broken pipe   # Traceback auf stderr, Lauf grün
```

(b) Eine Nachricht mit zwei Empfängern:

```
  accepted=['one@x.org', 'two@x.org']  (len=2) -- but it was 1 message
  second message refused 450 -> limit counts messages
```

(c) Ein Trap, dessen `deliver()` wirft (Unterklasse, absichtlich kaputt):

```
Exception occurred during processing of request from ('127.0.0.1', 33578)
  client: SMTPServerDisconnected: Connection unexpectedly closed
  probe reached this line, so nothing propagated out of the server
```

**Befund:** drei Abweichungen, alle in derselben Richtung — das Double nimmt mehr an bzw. verschweigt
mehr als ein echter Server.

* Eine unvollständige Nachricht wird gezählt und mit `250` quittiert. Ein Mailserver würde sie
  verwerfen.
* `limit` zählt **Nachrichten**, `accepted`/`throttled` zählen **Empfänger**. Im selben Objekt, ohne
  dass es irgendwo steht. Wer künftig `len(trap.accepted)` als Nachrichtenzahl liest, rechnet falsch,
  sobald eine Nachricht zwei Empfänger hat.
* Bricht das Double selbst, druckt `socketserver` einen Traceback und macht weiter. Für den
  Produktivcode sieht das aus wie **`SMTPServerDisconnected`**, also wie `_Outcome.UNREACHABLE` —
  „Server nicht erreichbar" ist aber ein Ergebnis, das die Suite an anderer Stelle ausdrücklich
  *erwartet*. Ein Test, der das prüft, wäre bei kaputtem Double aus dem falschen Grund grün.

**Folge:** heute keine. Es gibt genau einen Socket-Test, und der verlangt `attempts == 1` — ein
kaputtes Double liefert `attempts == 0` und der Test fällt. Der Befund ist deshalb eine Notiz, aber
eine mit Vorgeschichte: **R10-4 ist genau daran entstanden**, dass ein Double nachsichtiger war als
sein Gegenüber, und beim Bau des Ersatzes habe ich dieselbe Frage nicht gestellt. Die Lehre aus R10-4
war nicht auf das neue Double angewandt.

**Vorschlag:** (1) `handle_error` überschreiben, die Ausnahme auf dem Server sammeln und im Test
`assert trap.errors == []` — dann kann ein kaputtes Double keinen Test grün lassen. (2) Die beiden
Zähler benennen oder auf dieselbe Einheit bringen. (3) Eine abgebrochene `DATA` mit `451` ablehnen
statt zu zählen. Während des Reviews nicht getan (Regel 3).

### R15-3 · Eine Zeile der Befundtabelle nennt ihren Commit nicht

**Schwere:** Notiz
**Nachweis:** **gemessen**, `grep`: von allen Befundzeilen trägt genau eine „siehe unten" statt eines
Hashes — die von **R10-4** ([review.md:142](review.md)). Der Hash steht nur im Befundtext.

**Befund:** entstanden dadurch, dass der Hash erst nach dem Commit bekannt war und ich ihn im
Nachtrag (`c7dc26d`) nur an einer der beiden Stellen eingesetzt habe. Die Tabelle ist die Übersicht,
die jemand zuerst liest; eine Zeile, die auf „unten" verweist, kostet genau den Sprung, den die
Tabelle sparen soll.

**Vorschlag:** `8b238f6` in die Zeile. Während des Reviews nicht getan (Regel 3).

## 8.1 Negativraum des zweiten Laufs

**Gerendertes HTML gegen den Stand vor den Commits.** Acht Seiten (Index, Abstimmungsseite einfach und
mehrfach, Seite nach dem Token-Umzug, Manage, Success, Formular mit Fehlern, Ergebnisse) in einem
`git worktree` auf `3418317` und auf `HEAD` gerendert, csrf-Token maskiert, Hash pro Seite.
**Sieben von acht byte-identisch.** Die achte (Ergebnisse) unterscheidet sich in **genau vier Zeilen**,
und der Diff zeigt, dass es die zwei übersetzten `//`-Kommentare im Inline-Script sind — Kommentare in
einem `<script>` gehen mit an den Browser, das ist der ganze Unterschied. Keine K8-Änderung.

**Nicht-Python-Dateien.** `.gitignore`, `pyproject.toml`, der CI-Workflow und `main.css` nach dem
Entfernen aller Kommentare verglichen: **inhaltlich identisch**. (Bei `pyproject.toml` meldete das
Werkzeug einen Unterschied, weil mein Stripper nachgestellte Kommentare nicht entfernt; die Zeile ist
`"DTZ",` mit übersetztem Kommentar, der Wert unverändert.) Das war die K3-Frage: eine verschobene
`.gitignore`-Zeile oder ein verändertes `per-file-ignores` hätte keinen Fehler erzeugt.

**Die umbenannten Bezeichner.** `angenommen`, `vorige_spitze`, `HINWEIS`, `GEHAERTET` und die zwölf in
den Tests: `git grep` über Code, Templates, README **und Notizen** — keine Referenz auf die alten
Namen. Die Treffer in den Notizen sind deutsche Prosawörter („angenommen", „erwartet"), keine
Codeverweise.

**Hängende Verweise in der neuen Prosa.** Jeder in Backticks gesetzte Name aus allen Kommentaren und
Docstrings gegen den Codebestand geprüft (Skript, nicht Augenmaß): **0 von ihnen zeigt ins Leere.**
Das ist die Klasse, zu der der `R16-1`-Verschreiber gehörte, den ich vorher von Hand gefunden hatte.

**Der neue Socket-Test trägt.** Drei Mutationen an `mail.py`, jede einzeln:
`SMTPResponseException` aus dem `except` entfernt → **1 failed, 242 passed**, und der einzige
Fehlschlag ist dieser Test; `row.attempts += 0` → 3 failed; `return True` durch `continue` ersetzt →
2 failed. Der Test ist damit der **alleinige** Wächter über den Zweig, den ein echter drosselnder
Server trifft.

**Hygiene von `mailtrap`.** 50 Zyklen Öffnen/Verbinden/Schließen: Threads 1 → 1, Dateideskriptoren
4 → 4. Nach `__exit__` ist der Port frei (`ConnectionRefusedError`). Ein `with`-Block ohne eine
einzige Verbindung hängt nicht (die `shutdown()`-vor-`serve_forever()`-Falle greift nicht). `import
smtpd` → `ModuleNotFoundError`, die Begründung im Docstring stimmt.

**Behauptungen der neuen Notizen.** `mailtrap` wird von pytest nicht gesammelt (`--collect-only`:
0 Treffer, 262 Tests). `demockrazy/local_settings.py` ist ignoriert (`git check-ignore -v` nennt
`demockrazy/.gitignore:1`). Die Statuszeile „14 Commits" stimmt (14 Commits nennen eine Befundnummer).
Die Suite ist stabil: zwei Läufe hintereinander je 262.

**Ein Fehler in meiner eigenen Sonde, protokolliert weil er die Klasse zeigt.** Der erste
HTML-Vergleich meldete „identisch" — falsch: das `cd` in den Worktree galt für **beide** Läufe, die
Sonde hat den Vorzustand mit sich selbst verglichen. Aufgefallen ist es nur, weil die Hashes aus dem
Lauf davor noch dastanden und nicht dazu passten. Das ist **K4 am eigenen Werkzeug**, dieselbe Form wie
die Phase-0-Sonde, die „IDENTISCH" auf zwei identischen Tracebacks meldete. Konsequenz für das nächste
Mal: eine Vergleichssonde muss beweisen, dass sie zwei *verschiedene* Eingaben gesehen hat.

**Was dieser Lauf nicht geprüft hat.** Ob das Englisch *gut* ist — geprüft wurde, ob es *stimmt*. Der
Wortlaut der deutschen Betriebsausgabe (unverändert, per Entscheidung vom 2026-08-14). Ob
`vote/tests/mailtrap.py` in Produktion mit ausgeliefert wird — das hängt am NixOS-Modul und ist von
hier nicht sichtbar (Arbeitsregel 10, gehört nach [to-check.md](to-check.md)). Die übrigen Doubles
gegen ihr echtes Gegenüber (§7, Punkt 6) sind weiter offen; `recorded_sleep` und `locmem` sind nach
diesem Lauf sogar dringlicher, weil R10-5 zeigt, dass ich diese Frage auch beim Neubau nicht von
selbst stelle.
