# Handover – demockrazy-Modernisierung

**Für eine neue Session gedacht. Dies zuerst lesen, dann [plan.md](plan.md).**
**Stand: 2026-08-14** (die Zahlen unten sind an diesem Tag gemessen und wachsen mit jeder
Änderung nach -- R15-4 entstand daraus, dass sie stehen blieben). Branch `update/modernize-2026`,
106 Commits über `master` (Basis `3074dbb`). Arbeitsbaum sauber, **gepusht**, PR #1 offen. Die CI läuft
auf jeden Push (§4) und war bisher jedes Mal grün.

> **Das umfassende Review ist gelaufen und abgearbeitet** ([review.md](review.md), Plan §14).
> **29 Befunde, 27 behoben** in 16 Commits (`a1b5117` … `57574b9`), jeder mit der Befundnummer im
> Betreff. Die Suite ist von 215 auf **272** Tests gewachsen.
> **Es gab zwei Läufe:** der erste über den ganzen Branch (§5--§7 dort), der zweite über die Commits
> danach (§8) -- weil zwischen ihnen 1 200 Zeilen Prosa, eine neue Datei und ein neuer Test
> dazugekommen sind, alles von derselben Hand.
> Was noch **nicht geprüft** ist, steht in review.md §7 -- der Lauf hat alle 15 Kriterien einmal
> abgedeckt, nicht erschöpfend.
>
> **Der kritische Befund in einem Satz:** ein Doppelklick auf „Vote" ergab zwei Stimmen aus einem
> Token, weil die Token-Abfrage *außerhalb* der Transaktion stand -- 4 von 100 Runden gemessen.
> Behoben in `a1b5117`: die Löschung des Tokens ist jetzt die **Bedingung** für die Buchung, danach
> 0 von 100.
>
> **R2-1 ist nachgezogen:** der User hat bestätigt, dass es in Produktion ein Staff-Konto gibt --
> `/admin/` konnte damit Stimmzahlen editieren und jeden Token lesen. Beides ist zu (`5adb612`), und
> der User beschränkt `/admin/` am Proxy **aufs Intranet** -- damit ist das fehlende Rate-Limit auf
> `/admin/login/` gegenstandslos. Die zwei Hälften ersetzen sich nicht: die eine nimmt die
> Angriffsfläche von außen, die andere den Schaden von innen.
> **Offen sind zwei, beide außerhalb dieses Repos:** R8-1 (SMTP-Kennwort von 2023 -- der User prüft
> es vor dem Deploy) und R9-3 (ein Satz im Rollback-Verfahren) -- [to-check.md](to-check.md) A5, D5.
>
> **Beide Projektziele sind inhaltlich fertig** und das Bug-Register ist leer. Was noch offen ist,
> wartet auf eine Antwort des Users (§8) oder liegt außerhalb dieses Repos
> ([to-check.md](to-check.md) -- **neu aus dem Review: A4, A5, D5, D6**).

---

## 1. Was du in welcher Reihenfolge liest

| Datei | Wofür |
|---|---|
| **dieses Dokument** | Orientierung, Arbeitsregeln, offene Fragen, nächster Schritt |
| [plan.md](plan.md) | Der Plan mit allen Phasen, Bug-Nummern B1–B18, Fragen F1–F20. **Das Hauptdokument.** |
| **[review.md](review.md)** | **Das umfassende Review**: Umfang, Vorgehen, 15 Kriterien, die Fehlerklassen K1--K8, **29 Befunde mit Nachweis und Ergebnis**, Negativraum je Kriterium und in §7 das, was nicht geprüft ist. Geplant als plan.md §14 |
| **[to-check.md](to-check.md)** | **Alles, was außerhalb dieses Repos zu tun oder zu beantworten ist** – Proxy, NixOS-Modul, Prod-Node, offene Fragen. Mit Befehlen und Begründung. Die Liste für den User. |
| [deployment.md](deployment.md) | Wie Produktion wirklich läuft. **Vor jeder Settings-/Deploy-Änderung lesen.** |
| [phase-2-migrations.md](phase-2-migrations.md) | Warum die Migrations so aussehen, wie sie aussehen |
| [phase-0-baseline.md](phase-0-baseline.md) | Baseline-Messungen; enthält eine als überholt markierte Analyse |
| [baseline_probe.py](baseline_probe.py) | Das Phase-0-Probe-Skript; wurde zur Testsuite, bleibt als Referenz |

`baseline-schema.sql` ist ein überholtes Phase-0-Artefakt – maßgeblich ist `phase-2-migrations.md`.

## 2. Das Projekt in fünf Sätzen

Token-basiertes anonymes Abstimmungssystem in Django, produktiv als
`wahlcomputer.mayflower.de`. Jemand erstellt **ohne Login** eine Umfrage und gibt Wähler-Mailadressen
an; jede Adresse bekommt einen Einmal-Token per Mail. Die Stimmabgabe verbraucht den Token und
**löscht ihn** – deshalb gibt es keine Verbindung zwischen Wähler und Stimme. Die Umfrage schließt
automatisch, wenn alle Tokens verbraucht sind; erst dann sind die Ergebnisse sichtbar. Der Ersteller
hat einen separaten Management-Token und kann vorzeitig schließen.

**Die Anonymität ist das Kernversprechen.** Sie ist in `vote/tests/test_views.py::TestAnonymity`
abgesichert. Nichts darf sie aufweichen, ohne dass der User es ausdrücklich entscheidet. Wie das
beim Mailversand konkret aussieht -- und wo es die Fortschrittsanzeige beschnitten hat -- steht in §7.

## 3. Zwei Ziele – beide fertig – und ein Review

1. ✅ **Auf heutige Standards bringen.** Phase 0 bis 6 sind durch, **das Bug-Register ist
   vollständig abgearbeitet** (B9 als letzter, mit 3.9). Von 2.7 ist der größte Teil
   **gegenstandslos** geworden, nachdem der Proxy vorliegt: `forceSSL` und HSTS stehen dort schon,
   in Django wären sie doppelt. Was bleibt, betrifft den **Proxy, nicht dieses Repo** – §8, F15.
2. ✅ **Batch-Modus für Mails.** Gebaut: Warteschlange `OutgoingMail`, Management-Command
   `send_pending_mails`, **30er Batches mit 2 s Pause** (vom User vorgegeben, konfigurierbar).
   Details und Messungen in [plan.md](plan.md) §11.7, Zusammenfassung in §7.
   ⚠️ **Der systemd-Timer fehlt und liegt außerhalb dieses Repos** ([to-check.md](to-check.md) §C5)
   -- ohne ihn reiht Produktion nach dem Deploy ein und verschickt nie.
3. ✅ **Umfassendes Review** des ganzen Branches, [review.md](review.md) / Plan §14.
   29 Befunde, 27 behoben; die zwei offenen liegen außerhalb dieses Repos (A5, D5).

## 4. Umgebung und Verifikationsschleife

```bash
nix develop          # Python 3.13.13, Django 5.2.15, pytest, pytest-django, ruff
```

Nach jeder Änderung, komplett:

```bash
pytest
python3 manage.py check
python3 manage.py makemigrations --check --dry-run
ruff format --check .
ruff check .
```

Genau diese fünf Befehle fährt seit 5.3 auch die CI
([.github/workflows/checks.yml](../.github/workflows/checks.yml)), plus `nix flake check`. Wer hier
grün ist, ist dort grün.

**Sollwerte, an denen du merkst, dass alles in Ordnung ist:**

- `pytest` → **272 passed** (kein xfailed mehr, siehe §5; 215 waren es vor Phase 7). Die Zahl
  wächst mit jedem Fix -- wenn sie nicht stimmt, ist zuerst dieser Sollwert veraltet und nicht die
  Suite kaputt (R15-4)
- `manage.py check` → **no issues (0 silenced)**; die CI fährt es mit `--fail-level WARNING`,
  weil ein `Warning` den Rückgabecode sonst auf 0 lässt (Review R9-2)
- `makemigrations --check` → **No changes detected**
- `ruff format --check` → alle Dateien unverändert
- `ruff check` → **All checks passed** (seit 3.3 sauber, siehe §5)

Lokal starten (nicht mit `manage.py runserver` allein – siehe §6, Falle 3):

```bash
python3 manage.py runserver --settings=demockrazy.dev_settings
```

### Wo was liegt

| Pfad | Inhalt |
|---|---|
| [../vote/models.py](../vote/models.py) | `Poll`, `Choice`, `Token`, `PollType`, `OutgoingMail` (die Mail-Warteschlange); die zwei `UniqueConstraint`s, `get_absolute_url()` |
| [../vote/forms.py](../vote/forms.py) | `PollCreateForm` – Validierung der Erstellung, Dedup der Adressen, Empfänger-Deckel (3.8), `parse_lines()` |
| [../vote/views.py](../vote/views.py) | die sieben Views, nur noch Ablaufsteuerung; dazu der Token-Umzug aus der URL ins Cookie (3.9, B9) |
| [../vote/services/polls.py](../vote/services/polls.py) | `create_poll()` – Umfrage + Choices + Tokens per `bulk_create`, atomar |
| [../vote/services/mail.py](../vote/services/mail.py) | `poll_created_messages()` rendert, `enqueue()` reiht ein, `send_pending()` verschickt getaktet (§7). `deliver()` gibt es nicht mehr |
| [../vote/management/commands/send_pending_mails.py](../vote/management/commands/send_pending_mails.py) | Der Versender für den systemd-Timer -- dünn, die Arbeit steht im Service. Hält eine `flock`-Sperre |
| [../vote/templates/vote/mail/](../vote/templates/vote/mail/) | die vier Mail-Templates; **enden absichtlich ohne Zeilenumbruch** |
| [../vote/urls.py](../vote/urls.py) | die acht Routen als `path()`, dazu der eigene `identifier`-Converter |
| [../demockrazy/views.py](../demockrazy/views.py) | nur `/healthz` – Betriebs-Endpunkt, gehört nicht in `vote` |
| [../demockrazy/checks.py](../demockrazy/checks.py) | System-Check gegen stille Fehlkonfiguration der SQLite-`OPTIONS` (5.4) |
| [../demockrazy/tests/](../demockrazy/tests/) | Projektebene: `test_healthz`, `test_transactions` (was `ATOMIC_REQUESTS` wirklich tut), `test_staticfiles` (fährt `collectstatic` echt), `test_checks` |
| [../vote/migrations/](../vote/migrations/) | `0001`+`0002` rekonstruieren Prod von 2016, `0003` bringt Constraints und `choices`, `0004` die Mail-Warteschlange (rein additiv) |
| [../vote/tests/](../vote/tests/) | `test_models`, `test_forms`, `test_views`, `test_mail_service`, `test_poll_service`, `test_known_bugs`, `test_templates`, `test_send_pending_mails`, `test_admin`, `test_mailtrap`, `conftest` |
| [../vote/tests/mailtrap.py](../vote/tests/mailtrap.py) | Fake-SMTP-Server, selbst kein Test (wird von pytest nicht gesammelt) -- **aber getestet**, in `test_mailtrap.py`. Gegenüber des einen Tests, der wirklich über einen Socket spricht, **und** von Hand startbar: `python3 -m vote.tests.mailtrap 30 60` (R10-4, R15-2, R10-5) |
| [../demockrazy/settings.py](../demockrazy/settings.py) | Defaults; dazu `dev_settings.py` (runserver) und `test_settings.py` (pytest) |
| [../vote/static/](../vote/static/) | Bootstrap 5.3.8 und Chart.js 4.5.1, vendored. **In beiden Verzeichnissen liegt eine `PROVENANCE.md` – vor dem Anfassen lesen**, die Bundles sind bewusst um je eine Zeile geändert (`sourceMappingURL`), sonst bricht `collectstatic` ab |
| [../vote/templates/base.html](../vote/templates/base.html) | Navbar, Assets; kein jQuery mehr |

Zwei Dinge, die man beim ersten Blick in die Tests wissen will:

- **`conftest.py::create_poll` leert auch die Mail-Warteschlange** (mit `pause=0`). Seit §11.7
  verschickt `create()` nichts mehr, es reiht nur ein -- ohne diesen zweiten Schritt hätte kein Test
  eine Mail zu lesen. Wer prüfen will, dass der Request *selbst* nichts verschickt, nimmt nicht die
  Fixture, sondern postet direkt (siehe `test_views.py::TestCreateQueuesMails`).
  *(Hier stand ein Hinweis auf `django_capture_on_commit_callbacks` -- den braucht es nicht mehr,
  das `on_commit` ist entfallen.)*
- **`db.sqlite3` im Repo-Root ist ein veraltetes Phase-0-Artefakt** (gitignored) und hat noch die
  Spaltenreihenfolge einer zusammengefassten Migration. Nicht als Referenz für das Prod-Schema
  nehmen – dafür ist [phase-2-migrations.md](phase-2-migrations.md) zuständig.

## 5. Was absichtlich so ist – nicht „aufräumen"

**Nichts ist mehr rot** – das war eine Zeit lang anders und ist der Grund, warum dieser Abschnitt
existiert. `ruff check` ist seit 3.3 sauber: alle drei absichtlich roten Befunde sind über 3.2 und
3.3 weggefallen, weil die *Bugs* behoben wurden, deren Symptome sie waren. **Keiner wurde mit `noqa`
zugedeckt** – das ist die Regel, die hier gelten soll. **Das Ruff-Gate in der CI steht seit 5.3**,
ein neuer Befund macht den Build rot.

**Es gibt keinen `xfail`-Test mehr.** Der letzte war **B4** (`/vote/create` nahm 500 Empfänger
anstandslos an) und ist mit 3.8 gefallen – F5 hat den Deckel entschieden. Alle Tests in
[../vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py) stehen jetzt ohne Marker als
Regressionstests: B2, B3, B4, B6, B9, B10, B11, B12 und die zwei Unique-Constraints.
**Wer künftig einen Bug so spezifiziert, nimmt wieder `xfail(strict=True)`** – das Muster hat sich
bewährt: der Test beschreibt das Soll, schlägt fehl, und macht die Suite rot, sobald er behoben ist.
Merke aus 3.8: mit dem Marker kann auch die *Erwartung* fallen. Der B4-Test verlangte einen
ablehnenden Statuscode, solange die Maßnahme offen war; ein Formular-Deckel ergibt einen 200 mit
Fehlermeldung. Geprüft wird jetzt die Wirkung, nicht der Code.

**Drei** `per-file-ignores` in `pyproject.toml` sind ebenfalls Absicht und keine Nachlässigkeit:
`F403` für `demockrazy/settings.py` (der `from .local_settings import *` am Dateiende **ist** der
Konfigurationsmechanismus), `E501` für `test_mail_service.py` (schreibt den Mail-Wortlaut als
Literale aus, Umbrechen würde ihn um seinen Zweck bringen) und `RUF012` für `vote/models.py` (eine
Liste ist Djangos dokumentierte Schnittstelle für `Meta.constraints`).

## 6. Die Fallen – hier hätte ich Produktion kaputtgemacht

Produktion wird von einem NixOS-Modul `mayflower.demockrazy` gestartet, das **nicht in diesem Repo
liegt**. Vollständig in [deployment.md](deployment.md). Die vier Dinge, die man wissen muss:

**Falle 1 – `SECRET_KEY` darf nicht hart fehlschlagen.**
Das Modul generiert ein Settings-Modul `demockrazy_config`, das `from demockrazy.settings import *`
macht und den Key erst **danach** aus einer sops-Datei liest. Ein `os.environ["..."]` oder ein
`raise ImproperlyConfigured` in `settings.py` tötet den Service beim Start. Aktuell: Fallback auf
einen Zufallskey pro Prozess.

**Falle 2 – `SECURE_SSL_REDIRECT`/HSTS nicht anschalten, und zwar auch nicht im Modul.**
Die Node öffnet nur Port 80, TLS endet vorgelagert. **Seit die Proxy-Config vorliegt, ist das nicht
mehr nur eine Warnung, sondern erledigt:** dort steht `forceSSL = true` und ein HSTS-Snippet mit
einem Jahr. In Django wären beide **doppelt** – ein zweiter `Strict-Transport-Security`-Header ist
undefiniertes Verhalten, und `SECURE_SSL_REDIRECT` ohne `SECURE_PROXY_SSL_HEADER` eine
Redirect-Schleife. *(Hier stand „Diese Settings gehören ins Modul" – das war vor der Proxy-Config
und ist überholt: sie gehören nirgendwohin.)* `check --deploy` meckert deshalb dauerhaft über diese
zwei, und das ist richtig so. Was von 2.7 übrig ist, steht in [to-check.md](to-check.md) §B.

**Falle 3 – `DEBUG = False` ist jetzt Default**, deshalb startet nacktes `runserver` nicht.
Dafür gibt es `demockrazy/dev_settings.py`. Das ist kein Bug.

**Falle 4 – mein Code erreicht Prod nicht von allein.** Das Modul pinnt
`rev = 3074dbb` per `fetchFromGitHub`, und die Django-Version kommt aus der nixpkgs des
Colmena-Flakes, nicht aus `pyproject.toml`. **Zwei Änderungen im Repo des Users nötig:**
`rev`+`sha256` bumpen, und das Colmena-Flake auf `mf-next` (dort Django 5.2.15; `mf-stable` hat
4.2.28 und ist EOL). Darauf hinweisen, aber **nicht selbst ausrollen** (Regel 5).

## 7. Ziel 2 (Batch-Mails) – gebaut. Was dabei gilt

Diese Liste war die Vorarbeit, solange die Spec fehlte; sie ist jetzt das Protokoll dessen, was
umgesetzt wurde und was man beim Anfassen wissen muss. Vollständig in [plan.md](plan.md) §11.7.

1. ✅ **Erledigt mit 3.4, eingelöst mit §11.7:** Mail-Versand ist ein Service
   ([vote/services/mail.py](../vote/services/mail.py)). `poll_created_messages()` rendert,
   `enqueue()` reiht ein, `send_pending()` verschickt getaktet. **`deliver()` ist weg** -- es war
   genau die Stelle, die der Batch-Versender laut Plan ersetzen sollte.
2. ✅ **Anders eingelöst als geplant:** das `on_commit` von 3.4 ist entfallen. Das Einreihen läuft
   in **derselben Transaktion** wie die Tokens, und verschickt wird in einem anderen Prozess, der
   nur committete Zeilen sieht -- B7 hält damit strukturell statt über einen Callback.
3. ✅ **Erledigt mit 3.4:** Mail-Texte liegen als Templates in `vote/templates/vote/mail/`,
   Autoescaping aus, Wortlaut byteweise per Test festgenagelt.
4. ✅ **F8 ist entschieden: „lieber anonymer".** Kein dauerhafter Zustellstatus pro Adresse, keine
   Adressliste für den Ersteller. **Was daraus für eine Queue folgt, steht in [plan.md](plan.md)
   §11.4 – vor dem ersten Modell lesen.** Kurz: die Paarung Adresse↔Token muss bis zur Zustellung
   existieren, weil der Mailtext den Token enthält; sie wandert damit vom RAM auf die Platte, aber
   nur für die Dauer des Versands. Preisgegeben wäre *wer eingeladen wurde*, **nicht wie jemand
   gestimmt hat** – der Token wird bei der Abgabe gelöscht, die Stimme trägt keine Kennung.
   Aus demselben Grund loggt der Versender weder Adresse noch Umfragekennung; der Text einer
   SMTP-Exception kann die Adresse aber selbst enthalten. **Umgesetzt ist das jetzt** -- die Zeile
   trägt keine Poll-Kennung und keinen Zeitstempel und wird bei Erfolg gelöscht (§11.7).
5. ✅ **Missbrauchsschutz erledigt mit 3.8** (B4, F5): Deckel bei 150 Empfängern pro Umfrage,
   konfigurierbar. Ein Batch-Versender skaliert damit nicht den Missbrauch mit.
6. **Das Problem war gemessen, nicht vermutet** – [plan.md](plan.md) §11, der wichtigste
   Abschnitt für Ziel 2. Der Mailserver drosselt nach *Nachrichten pro Zeitfenster*
   (`450 4.7.1 too much mail from`; 30 gingen immer durch, bei 50 kam der Fehler), und der
   Versand lief **synchron im Request** – `on_commit` verschob ihn nicht, weil es ohne offenen
   `atomic`-Block sofort ausführt (Folge von B16).
7. ✅ **Eine SMTP-Verbindung statt einer pro Mail** (§11.6). Gemessen: 101 Nachrichten in 101
   Verbindungen → 101 in 1. Nicht die Kur, aber der billigste Schritt.
8. ✅ **Getakteter Versand gebaut** (§11.7): Warteschlange `OutgoingMail`, Service `send_pending()`,
   Command `send_pending_mails` mit `flock`-Sperre. **30er Batches, 2 s Pause – vom User vorgegeben**
   und über `DEMOCKRAZY_MAIL_BATCH_SIZE`/`_PAUSE` einstellbar. In §11.7 steht auch die Rechnung,
   warum 2 s zwischen den Batches die gemessene Grenze **nicht** einhält, und warum das tragbar ist:
   der `450` ist temporär, der Lauf bricht ab, der nächste Timer-Aufruf trifft ein zurückgesetztes
   Fenster. **Wenn die `450` im Log auftauchen: Pause auf 60.**
   ⚠️ **Der systemd-Timer fehlt noch** und liegt außerhalb dieses Repos – [to-check.md](to-check.md)
   §C5. Ohne ihn wird in Produktion nichts verschickt.
9. ✅ **Fortschrittsanzeige gebaut – aber kleiner als geplant, und zwar wegen F8** (§11.7 Punkt 7).
   Geplant war „n Einladungen dieser Umfrage warten noch". Das geht **nicht**: eine
   Warteschlangenzeile trägt keine Poll-Kennung, es gibt also keinen Weg, sie dieser Umfrage
   zuzuordnen, und eine indirekte Kennung würde nichts helfen -- wer die Warteschlange lesen kann,
   liest auch `vote_poll`. Gebaut ist die logisch sichere Richtung, als **Bit statt Zahl**: leere
   Warteschlange heißt, die Einladungen dieser Umfrage sind raus. Eine *Zahl* wäre eine Aussage über
   andere Umfragen, und die Manage-Seite braucht keinen Token.
10. Offen bleiben **Bounce-Handling** (hängt an F8 -- ein dauerhafter Status pro Adresse ist genau
   das, was nicht gespeichert werden soll) und **F20**.

**Wie man den Versand von Hand prüft** (dazugekommen mit R10-4, korrigiert mit R15-2). Die Suite
deckt ihn ab, aber sie spricht bis auf einen Test kein SMTP. Für die Fälle, die nur ein echter Server
zeigt -- Taktung, `450`, ein Server, der schweigt:

```bash
python3 -m vote.tests.mailtrap 30 60
```

Das ist `[limit] [window] [port]`, und es sind die Defaults: 30 Nachrichten pro 60 Sekunden auf Port
1025. Dazu in `demockrazy/local_settings.py` (gitignored über `demockrazy/.gitignore`):
`EMAIL_HOST = "127.0.0.1"`, `EMAIL_PORT = 1025`, **`EMAIL_USE_TLS = False`** und
`VOTE_SEND_MAILS = True`. Die dritte Zeile ist die Falle: der Default ist `True`, und ein
Debug-Server spricht kein STARTTLS.

Dann mehr als 30 Einladungen einreihen und `manage.py send_pending_mails --pause 1` laufen lassen: der
erste Lauf endet mit einem `450`, Zeilen bleiben liegen. **Der zweite Lauf muss in ein neues
Zeitfenster fallen** -- genau das tut der systemd-Timer in Produktion jede Minute. Gemessen mit einem
Fenster von 5 s (`... 30 5`), damit man nicht wartet: `5 verschickt, 0 aufgegeben, 3 warten noch`,
nach Ablauf des Fensters `3 verschickt, 0 aufgegeben, 0 warten noch`.

⚠️ **Nicht `0` als Fenster** -- das heißt „läuft nie ab", und dann verschickt jeder weitere Lauf
nichts, weil der Zähler stehenbleibt. Das war **R15-2**: der Trap hatte gar kein Fenster, meine
Anleitung sagte trotzdem „einfach zweimal laufen lassen", und der zehnte Lauf gibt die Einladung
auf (`MAX_ATTEMPTS`) -- eine Vorführung, die dem Leser das Gegenteil beibringt.

Der klassische Weg (`python -m smtpd -n -c DebuggingServer`) existiert nicht mehr: `smtpd` ist seit
Python 3.12 aus der Standardbibliothek. Nur die Mail-*Texte* ansehen geht einfacher, dafür genügt
`dev_settings.py` (Console-Backend).

## 8. Offene Fragen an den User

| # | Frage | Blockiert |
|---|---|---|
| **F15** | **Fast beantwortet.** Der Proxy liegt vor (Analyse in [deployment.md](deployment.md)): `forceSSL` + HSTS stehen dort, `SECURE_SSL_REDIRECT`/`SECURE_HSTS_SECONDS` sind damit gegenstandslos. **Es fehlt:** `services.nginx.recommendedProxySettings` auf dem Proxy-Host und der vollständige `proxyPass` – daran hängt, ob `X-Forwarded-Proto` ankommt. Warum das zählt: ohne den Header hält Django den Request für `http`, und die CSRF-Origin-Prüfung müsste **jede Stimmabgabe mit 403** abweisen. Sie tut es nicht, also liefert etwas das Schema. | **2.7** |
| ~~F8~~ | ~~Anonymität vs. Zustellstatus?~~ -> **"lieber anonymer".** Kein dauerhafter Status pro Adresse. Konsequenzen für die Queue in [plan.md](plan.md) §11.4 – **vor dem ersten Modell lesen.** | – |
| **F20** | **Wie hoch ist das Rate-Limit von `smtp.mayflower.de`?** Eingegrenzt: **30 gingen immer durch, bei 50 kam der 450er.** Gebraucht wird der Wert von `smtpd_client_message_rate_limit` (oder was eine Policy dort setzt), die Fensterlänge (`anvil_rate_time_unit`, Default 60 s) und die **vollständige** Fehlerzeile – der abgeschnittene Teil hinter *from* sagt, worauf gezählt wird (Client-IP oder Absenderadresse). Ohne diese Zahl wäre jede Taktung geraten. | **Ziel 2** |
| **F17** | Überschreibt das NixOS-Modul `VOTE_MAIL_SUBJECT`/`VOTE_MAIL_TEXT`/`VOTE_ADMIN_MAIL_*`? 3.4 hat sie aus `settings.py` entfernt, der Text kommt aus Templates. Ein Override dort wird nach dem Deploy still ignoriert. Prüfen mit `grep -rn 'VOTE_MAIL\|VOTE_ADMIN_MAIL'` im Colmena-Repo. | **vor dem Deploy** |

~~Kleinigkeit: die `type`-Spalte war in der Prod-Schema-Ausgabe abgeschnitten.~~ **Erledigt** –
`PRAGMA table_info(vote_poll)` auf Prod bestätigt `type varchar(20) NOT NULL` an Position 8 und
genau die Spaltenreihenfolge, die die zwei rekonstruierten Migrations erzeugen.

### So liest man die Prod-Datenbank

`sqlite3` liegt auf der Node nicht im Systemprofil -- das Modul installiert es nicht -- deshalb über
`nix run`. **Immer mit `-readonly`:** die Datei wird von vier uwsgi-Workern beschrieben, und ein
Leser hat dort nichts zu suchen außer zu lesen. Ein Leser nimmt kurz eine SHARED-Lock (bei diesen
Tabellengrößen Mikrosekunden); liegt ein hot journal herum, bricht die Verbindung mit
`SQLITE_READONLY_ROLLBACK` ab statt aufzuräumen.

```bash
nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 "PRAGMA table_info(vote_poll);"
```

✅ **Die Duplikat-Prüfung vor 3.6 ist gelaufen** (vom User, 2026-08-03): weder `vote_token.token_string`
noch `vote_poll.identifier` hat Duplikate, der Unique-Index in `0003` kann nicht auflaufen. Falls je
ein weiterer Unique-Constraint dazukommt, ist das die Vorlage:

```bash
nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 \
  "SELECT token_string, COUNT(*) c FROM vote_token GROUP BY token_string HAVING c>1;
   SELECT identifier,   COUNT(*) c FROM vote_poll  GROUP BY identifier   HAVING c>1;"
```

## 9. Nächster Schritt

**Phase 0 bis 6 sind durch, Phase 7 (das Review) ist offen und wartet auf den User.**
Das **Bug-Register ist leer** – B1 bis B18, zuletzt **B9** mit 3.9 (Token-Umzug aus dem
Query-String ins Cookie), dazu die zwei fehlenden Unique-Constraints. Ohne Häkchen steht nur noch
B14, und der ist inhaltlich in 2.7 aufgegangen. Mailversand und Poll-Erstellung sind Services, die
Umfrage-Erstellung kostet konstant 5 Statements, das Routing läuft über `path()`, und der Versand
läuft getaktet aus einer Warteschlange (§7).

Zwei Befunde aus dem Verlauf lohnen je zwei Sätze, weil sie Annahmen umstoßen -- wer hier
weiterarbeitet, läuft sonst in dieselben Fallen.

**B16 ist bei 5.5 aufgefallen und lohnt zwei Sätze, weil es Annahmen umstößt:**
`ATOMIC_REQUESTS = True` stand seit 2016 **modulweit** in `settings.py`, Django liest es aber pro
Datenbank – die Option war zehn Jahre lang wirkungslos, in Produktion auch. **Es gibt also keine
Transaktion um einen Request.** Atomar sind nur `create_poll()` und der `atomic()`-Block in
`vote()`, beide explizit und getestet. Wer hier etwas über Transaktionen annimmt, prüft es an
[../demockrazy/tests/test_transactions.py](../demockrazy/tests/test_transactions.py) nach.
Der Befund hat B7s Begründung, B13s Risikoeinschätzung und die 3.5-Notiz korrigiert. **F18 ist
inzwischen beantwortet: nein** – gemessen, dass die Option die Teilstimme aus `vote()` gar nicht
zurückrollen würde, weil die View den `KeyError` selbst fängt und eine 200-Seite liefert. Der
explizite Block leistet also etwas, das `ATOMIC_REQUESTS` nicht kann.

**B17 lohnt ebenfalls zwei Sätze, weil es eine Falle ist, die kein Test sah:**
**mehrzeilige `{# … #}` sind in Django keine Kommentare** (`tag_re` ohne `re.DOTALL`). Sie landen
als Text im Output, samt der `{{ … }}` darin, die dann ausgewertet werden. Drei Vorkommen gab es;
zwei fielen nie auf, weil sie *außerhalb* der `{% block %}`s eines Kind-Templates standen und Django
das verwirft. Beim dritten stand „script" in spitzen Klammern in der Prosa – der Parser öffnete
daran ein `script`-Element und verschluckte das Datenelement dahinter: **200 ohne Diagramm, und
`curl` sah korrekt aus.** Erst der DOM im Browser zeigte es. Für mehrzeiliges gibt es
`{% comment %}`; [../vote/tests/test_templates.py](../vote/tests/test_templates.py) wacht darüber.
**Lehre fürs Weiterarbeiten: bei JS- oder Markup-Änderungen im Browser gegenprüfen**, nicht nur
`pytest` und `curl`. `.claude/launch.json` (gitignored) startet den Dev-Server dafür.

### Was als nächstes dran ist

**Im Repo ist nichts offen.** Phase 7 ist durch: 7.1 hat 24 Befunde ergeben, 7.2 hat 22 davon
behoben; der Nachtrag R10-4 und der zweite Lauf (review.md §8) haben fünf weitere ergeben, alle
behoben -- zusammen 29 Befunde, 27 davon behoben. Was übrig ist, braucht eine Antwort von dir -- **[to-check.md](to-check.md) A1 (F17) und A5
(SMTP-Kennwort, prüfst du vor dem Deploy)** -- oder ist ein Handgriff außerhalb dieses Repos, allen
voran weiter der **systemd-Timer** (§C5), ohne den nach dem Deploy keine Mail rausgeht, und die
Intranet-Beschränkung für `/admin/` (letzter Handgriff zu R2-1, entschieden -- §A4).

**Eine Zahl aus 7.2 gehört dir vorgelegt:** `VOTE_MAX_CHOICES` = 100 (Befund R7-1, Commit `3e89f0c`)
ist von mir gewählt, nicht von dir -- anders als die 150 für Empfänger. Real vorkommende Umfragen
haben eine Handvoll Antwortmöglichkeiten; über 1 000 wäre eine multiple_choice-Umfrage ohnehin nicht
mehr abstimmbar. Änderbar über `DEMOCKRAZY_MAX_CHOICES`.

**Was das Review *nicht* abgedeckt hat, steht in review.md §7** -- vor allem die **Testsuite als
Text** (das Urteil über sie stützt sich auf die Mutationssonde, nicht auf eine Lektüre aller Tests)
und der **Branch als Verlauf** (geprüft sind der Ist-Zustand und der Gesamtdiff, nicht Commit für
Commit). Wer dort weitermacht, findet die Sonden in [review_probes.py](review_probes.py).

Zwei Beobachtungen aus dem Lauf, die über die Einzelbefunde hinausgehen:
**das Gefährliche stand nicht in der Logik, sondern an ihren Rändern** (Doppelklick, Zeilenumbruch im
Titel, krummer Query-Parameter -- die Logik selbst hat gehalten), und **die Gegenmaßnahmen gegen K1
hatten selbst K1**: der Härtungs-Check prüft `transaction_mode` nicht auf den Wert (R9-1) und macht
als `Warning` nichts rot (R9-2). Wer eine Prüfung baut, muss sie kaputtmachen, um zu wissen, ob sie
greift -- die 26 Mutationen waren der produktivste Teil des Laufs (21 bemerkt, 5 nicht).

**Sonst ist im Repo nichts offen.** Beide Ziele sind inhaltlich fertig (§3). Was übrig ist, wartet
auf eine Antwort (§8: F15, F17, F20) oder liegt außerhalb dieses Repos
([to-check.md](to-check.md)) -- **darunter der systemd-Timer, ohne den nach dem Deploy keine Mail
rausgeht.** Nichts davon lässt sich hier erledigen.

Was beim Routing (3.7) zu beachten war und weiter gilt, falls jemand `urls.py` anfasst:
die sieben öffentlichen Pfade sind **zeichengleich** zu halten (Regel 5), `test_views.py::TestUrls`
prüft sie zusammen mit dem Converter-Verhalten. Der Namespace `polls` und die `reverse()`-Namen
(`vote:index`, `vote:create`, `vote:polls:*`) sind in Templates **und** im Mail-Service verdrahtet.
`<slug:…>` ist für die Kennung kein Ersatz – es lässt `-` und `_` zusätzlich zu; deshalb steht in
[../vote/urls.py](../vote/urls.py) ein eigener Converter mit `regex = "[a-zA-Z0-9]+"`.

### Vor dem Deploy (nicht von mir, Regel 7)

**Vollständig und mit Befehlen in [to-check.md](to-check.md)** – dort steht alles, was außerhalb
dieses Repos passieren muss, nach Ort gruppiert (Proxy / Modul / Node / Antwort an mich). Kurzfassung:

1. **F17 klären** – der `grep` nach `VOTE_MAIL` im Deployment-Repo. **Der einzige Punkt, der noch
   eine Antwort braucht**; die übrigen sind Handgriffe.
2. **Die SQLite-`OPTIONS` ins Modul übernehmen** (5.4). Geht sonst still verloren, weil
   `demockrazy_config` `DATABASES` neu setzt – derselbe Mechanismus wie B16. Danach
   `DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check` fahren, das meldet es.
3. **`rev`+`sha256` bumpen** und das Colmena-Flake auf `mf-next` (§6, Falle 4).
4. **`0003` ist kein No-Op** – schreibt `vote_poll` und `vote_token` neu, gegen ein Prod-Abbild
   geprüft ([phase-2-migrations.md](phase-2-migrations.md)). Läuft im `preStart`, Backup liegt vor.
5. **`/healthz`** braucht einen `Host`-Header, den `ALLOWED_HOSTS` akzeptiert.

Am Proxy, unabhängig vom Deploy: den vorhandenen **CSP-Snippet** einbinden (geht erst, seit alles
vendored ist), den **widersprüchlichen `X-Frame-Options`** entwirren – Proxy sagt `sameorigin`,
Django `DENY`, beide Header gehen raus – und das **`log_format` ohne `$args`** setzen, das ist der
Rest von B9: der Token zieht seit 3.9 nach *einem* Aufruf in ein Cookie um, und die Logzeile genau
dieses Aufrufs ist nur dort zu lösen. Alle drei in [to-check.md](to-check.md) §B.

## 10. Arbeitsregeln (haben sich bewährt, bitte beibehalten)

1. **Kleine, thematisch geschlossene Commits.** Ein Commit = ein Planpunkt. Formatierung und
   Verhaltensänderung nie im gleichen Commit.
2. **Commit-Nachrichten auf Englisch, Prosa, erklären *warum*** – nicht nur was. Ende jeder
   Nachricht: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
3. **Kommunikation mit dem User auf Deutsch. Notizen auf Deutsch. Code auf Englisch** – Bezeichner,
   Kommentare, Docstrings, Commit-Nachrichten. Der Bestand ist mit `58e86c5` und `52de7bc`
   nachgezogen, es steht kein deutscher Kommentar mehr im Code.
   **Ausnahme, vom User am 2026-08-14 entschieden: Betriebsausgabe bleibt deutsch.** Also die
   Logzeilen in [mail.py](../vote/services/mail.py), `--help` und die Zusammenfassung von
   `send_pending_mails`, der `hint` in [checks.py](../demockrazy/checks.py) und
   `OutgoingMail.__str__`. Das liest ein Mensch im Journal oder auf einem Terminal, es ist keine
   Code-Prosa – und drei Tests prüfen genau auf diese Zeichenketten (`"läuft schon"`,
   `"2 verschickt"`, `"kommt nicht voran"`). Wer den Code das nächste Mal durchgeht, lässt sie
   stehen. Der deutsche Mail-Wortlaut ist ohnehin Prüfgegenstand (Regel 3/6).
4. **Nicht raten, messen.** Versionsnummern gegen nixpkgs prüfen, Prod-Verhalten simulieren statt
   annehmen. Das hat mehrfach falsche Schlüsse verhindert – u. a. hätte ich fast eine
   zusammengefasste Migration eingecheckt, die ein anderes Schema beschreibt als das laufende.
5. **URLs sind stabil zu halten.** Es sind Mails mit `?token=`-Links auf bestehende Umfragen
   unterwegs. `/vote/<identifier>/…` darf sich nicht ändern; abgesichert in
   `test_views.py::TestUrls`.
6. **Verhalten erhalten, außer wo als Bug markiert.** Keine stillen Änderungen an Mail-Texten,
   Token-Längen, URL-Struktur.
7. **Kein Rollout.** Änderungen am Deploy vorbereiten und benennen, ausrollen tut der User.
8. **Wenn ein Befund sich als falsch erweist: korrigieren, auch in den Notizen.** Es steht schon
   eine als überholt markierte Analyse in `phase-0-baseline.md` – so gehandhabt, nicht gelöscht,
   weil die Analyse selbst noch nützlich ist.
9. **Bei Unklarheit:** alles erledigen, was nicht davon abhängt, die Frage in `plan.md` §12
   festhalten und beim nächsten Bericht stellen.
10. **Im Workspace bleiben.** Arbeiten *und suchen* nur in
   `~/Desktop/wahlcomputer-update/demockrazy`. Nicht im übrigen Dateisystem stöbern, auch nicht,
   um eine Frage schneller selbst zu klären. **Was von außen gebraucht wird, beim User erfragen** –
   er liefert es und hat das ausdrücklich angeboten. So sind F12 (Prod-Schema), die Duplikat-Prüfung
   vor 3.6 und der `PRAGMA`-Nachtrag gelaufen; F17 wartet noch darauf. Betrifft insbesondere: das
   NixOS-Modul `mayflower.demockrazy`, das Colmena-Repo, alles auf der Prod-Node.
   Ausnahme sind offensichtlich projektbezogene Werkzeugaufrufe (`nix`, `git`, PyPI-/nixpkgs-Abfragen).
11. **Code-Kommentare und Docstrings sehr kurz** – ein bis zwei Zeilen, die auf die Begründung
   *zeigen*, statt sie zu enthalten: `Plan §11.7`, `B9`, `F8`. Vom User am 2026-08-04 ausdrücklich
   gewünscht, nachdem ein 14-zeiliger Kommentar an einem einzigen `exists()`-Aufruf stand.
   **Die Notizen bleiben ausführlich** – dort gehört die Argumentation hin, und dann steht sie an
   genau einer Stelle. *(Aus früheren Commits stehen noch lange Docstrings in
   `vote/services/mail.py` und `vote/models.py`; kürzen ist angeboten, nicht beauftragt.)*
   **Diese Regel steht absichtlich hinten:** die Nummern 1–10 sind in Notizen *und* Code
   Hunderte Male referenziert, Einsortieren hätte jeden Verweis verschoben.

## 11. Wichtige Erkenntnisse, die nicht offensichtlich sind

- **Django 4.2 → 5.2 ist für diesen Code verhaltensneutral.** In Phase 0 mit 21 Fällen auf beiden
  Versionen gegengeprüft: identische Statuscodes, Redirects, Mails, Tokenlängen. Kein
  Schema-Drift, keine neuen Deprecations. Das Risiko lag nie in der Version, sondern in den
  Altlasten.
- **Prod-Migrationshistorie ist von 2016** und hat zwei Einträge. Die eingecheckten `0001`/`0002`
  reproduzieren sie namensgleich, werden dort also übersprungen. **Achtung, seit 3.6 gilt der
  frühere Satz „`migrate` ist ein garantierter No-Op" nicht mehr:** `0003` wird angewendet und
  **schreibt `vote_poll` und `vote_token` neu** (so hängt SQLite einen Constraint an). Gegen ein
  Abbild des Prod-Schemas geprüft: Daten unversehrt, FKs konsistent, Spaltenreihenfolge unverändert
  – [phase-2-migrations.md](phase-2-migrations.md).
- **Das k8s-Setup (`briefwahl.mayflower.cloud`) ist abgeschaltet** und in `4e15012` entfernt.
  Bestätigt risikofrei: das Prod-Modul konsumiert keine Flake-Outputs dieses Repos, nur den
  Quelltext. Falls sich das doch als falsch erweist: `git revert 4e15012`.
- **Der Mayflower-nixpkgs-Fork existiert wegen der `mayflower.*`-NixOS-Module.** Ein Wechsel auf
  upstream nixpkgs hätte den Deploy gebrochen – der User hat mich rechtzeitig auf `mf-next`
  umgelenkt. Input bleibt `github:mayflower/nixpkgs/mf-next`.
- **`.gitignore` hatte zehn Jahre lang die Quell-Assets der App ausgeschlossen** (B18): die Regel
  hieß `static/` statt `/static/` und traf damit auch `vote/static/`, nicht nur `STATIC_ROOT`.
  Getrackt war dort nur, was älter als die Regel war; jedes neue Asset fiel still heraus. Beim
  Vendoren von Bootstrap 5 wäre die Folge gewesen: **Produktion ohne CSS.** Wer im Frontend etwas
  hinzufügt, prüft nach `git add`, ob die Datei wirklich im `git status` steht.
- **Mehrzeilige `{# … #}` sind keine Kommentare** (B17). Steht in §9 mit dem ganzen Hergang; hier nur
  die Kurzform, weil man es sonst zweimal lernt.
- **Die Referrer-Policy gibt den Query-String weiter, und das war die Hälfte von B9.** Django
  schickt `Referrer-Policy: same-origin`; unter dieser Policy sendet der Browser für
  **gleichherkünftige** Anfragen die *vollständige* URL. Im Browser gemessen: `document.referrer`
  enthielt den kompletten Query-String. Ein `?token=…` reiste damit nicht nur in *einer* Logzeile,
  sondern im `Referer` jeder Unteranfrage der Seite mit – Stylesheet inklusive. **Wer eine URL für
  „nur einmal geloggt" hält, irrt.** Mit 3.9 ist die Adresse nach dem ersten Aufruf token-frei.
- **Cookies waren für die Stimmabgabe schon vorher Pflicht** – gemessen, nicht angenommen: ein POST
  ohne Cookie ist ein **403**, weil Djangos CSRF-Prüfung eines verlangt. Das ist das Argument, mit
  dem 3.9 den Token in ein Cookie legen darf, ohne jemandem etwas wegzunehmen. Wer so etwas ändern
  will, prüft es an `test_views.py::TestTokenLeavesTheUrl` nach.
- **Ein langlaufender Schreiber ist harmlos, eine lange Transaktion nicht.** Für Ziel 2 gemessen
  (plan.md §11.7, Punkt 4a): ein Versender, der minutenlang läuft und zwischen den Batches schläft,
  kostet die gleichzeitige Stimmabgabe **7–9 ms** – solange `sleep` außerhalb jeder Transaktion
  steht. Wandert der `sleep` *in* ein `atomic()`, dauern Stimmen Sekunden, und sobald der Lauf länger
  wird als der `timeout` von 20 s, gehen sie verloren (gemessen: 8 von 200). **Die Länge eines
  Prozesses ist also nicht das Problem, die Länge einer Transaktion ist es.**
- **`EMAIL_TIMEOUT` musste gesetzt werden, weil Djangos Default unbegrenzt wartet.** Bei `None` gibt
  das SMTP-Backend den Timeout nicht an `smtplib` weiter, das nimmt den Socket-Default, und der ist
  auch `None`. Ein Mailserver, der annimmt und dann schweigt, hätte einen der vier uwsgi-Prozesse
  gehalten. Steht jetzt auf 10 s (`DEMOCKRAZY_MAIL_TIMEOUT`), festgehalten in
  `test_mail_service.py::TestSendPending`.
- **`processes = 4` im uwsgi auf einer SQLite-Datei** ist genau das Lock-Szenario aus B13.
  ✅ **Mit 5.4 gehärtet** – aber der entscheidende Schalter war nicht WAL, sondern
  `transaction_mode="IMMEDIATE"`: bei Djangos `DEFERRED` muss eine Transaktion, die erst liest und
  dann schreibt (die Form von `vote()`), ihre Sperre hochstufen, und **das kann SQLite nicht warten
  lassen** – sofortiges `SQLITE_BUSY`, ohne Rücksicht auf `timeout`. Gemessen: mit den Defaults
  scheitern **164 von 200** gleichzeitigen Stimmabgaben, mit der Härtung keine.
  ⚠️ **Die Optionen erreichen Prod nicht von allein** (`demockrazy_config` setzt `DATABASES` neu –
  derselbe Mechanismus wie B16), deshalb gibt es dafür einen System-Check. Siehe
  [to-check.md](to-check.md) §C3.
