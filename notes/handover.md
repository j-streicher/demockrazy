# Handover – demockrazy-Modernisierung

**Für eine neue Session gedacht. Dies zuerst lesen, dann [plan.md](plan.md).**
Stand: Ende 2026-08-03, Branch `update/modernize-2026`, 41 Commits über `master` (Basis `3074dbb`).
Arbeitsbaum ist sauber, alles committed, **nichts gepusht** -- die CI hat also noch nie gelaufen,
sie greift erst beim ersten Push.

---

## 1. Was du in welcher Reihenfolge liest

| Datei | Wofür |
|---|---|
| **dieses Dokument** | Orientierung, Arbeitsregeln, offene Fragen, nächster Schritt |
| [plan.md](plan.md) | Der Plan mit allen Phasen, Bug-Nummern B1–B15, Fragen F1–F17. **Das Hauptdokument.** |
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
abgesichert. Nichts darf sie aufweichen, ohne dass der User es ausdrücklich entscheidet – das ist
insbesondere für Ziel 2 relevant (§7).

## 3. Zwei Ziele

1. **Auf heutige Standards bringen.** Phase 0, 1 und 2 (außer 2.7) sind fertig, Phase 3 ist bis
   3.6 durch, CI steht (5.3). Offen: 3.7/3.8, Phase 4, 5.4/5.5.
2. **Batch-Modus für Mails.** *Spec steht noch aus, der User erklärt sie später.* Nicht spekulativ
   bauen. Phase 3 so anlegen, dass es andockt (§7).

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

- `pytest` → **141 passed, 1 xfailed**
- `manage.py check` → **no issues (0 silenced)**
- `makemigrations --check` → **No changes detected**
- `ruff format --check` → alle Dateien unverändert
- `ruff check` → **All checks passed** (seit 3.3 sauber, siehe §5)

Lokal starten (nicht mit `manage.py runserver` allein – siehe §6, Falle 3):

```bash
python3 manage.py runserver --settings=demockrazy.dev_settings
```

### Wo was liegt (Stand nach Phase 3.6)

| Pfad | Inhalt |
|---|---|
| [../vote/models.py](../vote/models.py) | `Poll`, `Choice`, `Token`, `PollType`; die zwei `UniqueConstraint`s, `get_absolute_url()` |
| [../vote/forms.py](../vote/forms.py) | `PollCreateForm` – Validierung der Erstellung, Dedup der Adressen, `parse_lines()` |
| [../vote/views.py](../vote/views.py) | die sechs Views, nur noch Ablaufsteuerung |
| [../vote/services/polls.py](../vote/services/polls.py) | `create_poll()` – Umfrage + Choices + Tokens per `bulk_create`, atomar |
| [../vote/services/mail.py](../vote/services/mail.py) | `poll_created_messages()` rendert, `deliver()` verschickt |
| [../vote/templates/vote/mail/](../vote/templates/vote/mail/) | die vier Mail-Templates; **enden absichtlich ohne Zeilenumbruch** |
| [../vote/migrations/](../vote/migrations/) | `0001`+`0002` rekonstruieren Prod von 2016, `0003` bringt Constraints und `choices` |
| [../vote/tests/](../vote/tests/) | `test_models`, `test_forms`, `test_views`, `test_mail_service`, `test_poll_service`, `test_known_bugs`, `conftest` |
| [../demockrazy/settings.py](../demockrazy/settings.py) | Defaults; dazu `dev_settings.py` (runserver) und `test_settings.py` (pytest) |

Zwei Dinge, die man beim ersten Blick in die Tests wissen will:

- **`conftest.py::create_poll` führt die `on_commit`-Callbacks aus.** Ohne das käme in einem
  `django_db`-Test nie eine Mail an, weil die Testtransaktion nicht committet (3.4). Wer einen
  neuen Test schreibt, der Mails erwartet, braucht `django_capture_on_commit_callbacks`.
- **`db.sqlite3` im Repo-Root ist ein veraltetes Phase-0-Artefakt** (gitignored) und hat noch die
  Spaltenreihenfolge einer zusammengefassten Migration. Nicht als Referenz für das Prod-Schema
  nehmen – dafür ist [phase-2-migrations.md](phase-2-migrations.md) zuständig.

## 5. Was absichtlich rot ist – nicht „aufräumen"

**`ruff check` ist seit 3.3 sauber** – alle drei absichtlich roten Befunde sind über 3.2 und 3.3
weggefallen, weil die Bugs behoben wurden, deren Symptome sie waren. Keiner wurde mit `noqa`
zugedeckt. **Das Ruff-Gate in der CI steht seit 5.3** – ein neuer Befund macht den Build rot.

**Ein `xfail(strict=True)`-Test** ist noch übrig, in
[../vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py): **B4** – `/vote/create` nimmt
500 Empfänger anstandslos an. Er schlägt heute fehl und braucht F5. **Wenn du den Bug behebst, wird
die Suite rot** – das ist Absicht und die Erinnerung, den Marker zu entfernen. Nicht der Marker ist
das Problem. Die Tests für die behobenen B2, B3, B6, B11, B12 und die zwei Unique-Constraints stehen
in derselben Datei ohne Marker als Regressionstests.

Zwei `per-file-ignores` in `pyproject.toml` sind ebenfalls Absicht und keine Nachlässigkeit:
`E501` für `test_mail_service.py` (schreibt den Mail-Wortlaut als Literale aus) und `RUF012` für
`vote/models.py` (eine Liste ist Djangos Schnittstelle für `Meta.constraints`).

## 6. Die Fallen – hier hätte ich Produktion kaputtgemacht

Produktion wird von einem NixOS-Modul `mayflower.demockrazy` gestartet, das **nicht in diesem Repo
liegt**. Vollständig in [deployment.md](deployment.md). Die vier Dinge, die man wissen muss:

**Falle 1 – `SECRET_KEY` darf nicht hart fehlschlagen.**
Das Modul generiert ein Settings-Modul `demockrazy_config`, das `from demockrazy.settings import *`
macht und den Key erst **danach** aus einer sops-Datei liest. Ein `os.environ["..."]` oder ein
`raise ImproperlyConfigured` in `settings.py` tötet den Service beim Start. Aktuell: Fallback auf
einen Zufallskey pro Prozess.

**Falle 2 – `SECURE_SSL_REDIRECT`/HSTS nicht anschalten.**
Die Node öffnet nur Port 80, TLS endet vorgelagert. Ohne `SECURE_PROXY_SSL_HEADER` erzeugt das eine
Redirect-Schleife. Diese Settings gehören ins Modul. **Blockiert 2.7, siehe F15.**

**Falle 3 – `DEBUG = False` ist jetzt Default**, deshalb startet nacktes `runserver` nicht.
Dafür gibt es `demockrazy/dev_settings.py`. Das ist kein Bug.

**Falle 4 – mein Code erreicht Prod nicht von allein.** Das Modul pinnt
`rev = 3074dbb` per `fetchFromGitHub`, und die Django-Version kommt aus der nixpkgs des
Colmena-Flakes, nicht aus `pyproject.toml`. **Zwei Änderungen im Repo des Users nötig:**
`rev`+`sha256` bumpen, und das Colmena-Flake auf `mf-next` (dort Django 5.2.15; `mf-stable` hat
4.2.28 und ist EOL). Darauf hinweisen, aber **nicht selbst ausrollen** (Regel 5).

## 7. Vorarbeit für Ziel 2 (Batch-Mails) – nicht vorgreifen, aber freihalten

Die Spec kommt vom User. Was für *jede* Variante gilt und in Phase 3 entstehen soll:

1. ✅ **Erledigt mit 3.4:** Mail-Versand ist ein Service ([vote/services/mail.py](../vote/services/mail.py)).
   `poll_created_messages()` rendert, `deliver()` verschickt. **Ein Batch-Versender ersetzt
   `deliver()`** und lässt das Rendern unberührt.
2. ✅ **Erledigt mit 3.4:** Versand hängt an `transaction.on_commit()`, der Callback rührt die
   Datenbank nicht an (B7).
3. ✅ **Erledigt mit 3.4:** Mail-Texte liegen als Templates in `vote/templates/vote/mail/`,
   Autoescaping aus, Wortlaut byteweise per Test festgenagelt.
4. **Zielkonflikt, den nur der User auflösen kann (F8):** ein Batch-Modus mit Retry/Zustellstatus
   braucht „welche Adresse wurde erfolgreich zugestellt". Genau diese Zuordnung wird heute
   *absichtlich nicht* gespeichert. **Kein Modell dafür entwerfen, bevor das entschieden ist.**
   Aus demselben Grund loggt `deliver()` weder Adresse noch Umfragekennung; der Text einer
   SMTP-Exception kann die Adresse aber selbst enthalten. Mit F8 zu bewerten.
5. **Missbrauchsschutz zuerst (B4/F5):** `/vote/create` hat keinerlei Auth und kein Rate-Limit.
   Jeder kann beliebig viele Mails über den Mayflower-SMTP verschicken. Ein Batch-Versender
   darüber wäre ein Spam-Werkzeug.

## 8. Offene Fragen an den User

| # | Frage | Blockiert |
|---|---|---|
| **F15** | Setzt der vorgelagerte Proxy `X-Forwarded-Proto`? Gibt es ein Mayflower-Default für `SECURE_PROXY_SSL_HEADER`? Nebenrätsel: seit Django 4.0 wird der `Origin`-Header strikt geprüft – ohne Proxy-Header müssten POSTs (also **jede Stimmabgabe**) mit 403 scheitern; sie tun es offenbar nicht, also liefert irgendwas das Schema. Das will ich verstanden haben. | **2.7** |
| **F4** | Highcharts 4.2.5 ist vendored und **proprietär lizenziert** (kein FOSS-Modell für kommerzielle Nutzung) in einem MIT-Repo. Existiert eine Lizenz, oder ersetzen (Chart.js MIT / ECharts Apache-2.0)? | **4.3** |
| **F5** | Zugangsschutz für `/vote/create` – Login, Invite-Code, IP-Rate-Limit, Empfänger-Deckel? | 3.8, Ziel 2 |
| **F8** | Anonymität vs. Zustellstatus pro Empfänger – wie weit darf Ziel 2 das aufweichen? | Ziel 2 |
| **F13** | Wie groß sind Abstimmungen real (Empfänger pro Poll, parallele Polls)? Entscheidet SQLite-Tuning vs. Postgres (B13) und die Batch-Größen. | 5.4, Ziel 2 |
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

**Phase 3 ist bis 3.6 durch, CI steht (5.3).** Behoben: **B1, B2, B3, B5, B6, B7, B11, B12, B15**
und die zwei fehlenden Unique-Constraints. Mailversand und Poll-Erstellung sind Services, der
Versand hängt an `on_commit`, die Umfrage-Erstellung kostet konstant 5 Statements.
**Die Vorarbeit für Ziel 2 (§7.1–3) ist vollständig** – ein Batch-Versender ersetzt `mail.deliver()`.

### 3.7 – `re_path` → `path` (nicht blockiert, klein)

In [../demockrazy/urls.py](../demockrazy/urls.py) und [../vote/urls.py](../vote/urls.py).
Das Wesentliche vorab, damit es nicht schiefgeht:

- **Die URLs müssen zeichengleich bleiben** (Regel 5): `/vote/`, `/vote/create`,
  `/vote/<id>/`, `/vote/<id>/vote`, `/vote/<id>/success`, `/vote/<id>/manage`, `/vote/<id>/results`.
  `test_views.py::TestUrls` prüft genau diese sieben.
- **`slug` ist kein Ersatz** für `(?P<poll_identifier>[a-zA-Z0-9]+)`: `slug` erlaubt zusätzlich `-`
  und `_`, würde also mehr annehmen als heute. Es braucht einen eigenen Converter
  (`regex = "[a-zA-Z0-9]+"`), am sinnvollsten in `vote/urls.py` und per `register_converter`.
- Das `include(pollpatterns)`-Muster mit dem Namespace `polls` bleibt, wie es ist; die
  `reverse()`-Namen (`vote:index`, `vote:create`, `vote:polls:*`) sind in Templates **und** im
  Mail-Service verdrahtet.
- Nach dem Umbau lohnt eine Gegenprobe mit einem Identifier, der ein `-` enthält: der muss weiter
  404 geben und nicht plötzlich matchen.

### Danach

Von Phase 3 bleibt nur **3.8** (Zugangsschutz, braucht F5). Sonst unblockiert: **5.5** (`/healthz`),
**Phase 4** außer 4.3 (Frontend: Bootstrap 5, jQuery raus, Cache-Busting, Template-Kleinkram).

### Vor dem Deploy (nicht von mir, Regel 7)

1. **F17 klären** – der `grep` im Colmena-Repo (§8).
2. **`0003` ist kein No-Op.** Es schreibt `vote_poll` und `vote_token` neu; geprüft gegen ein
   Prod-Abbild, Daten unversehrt ([phase-2-migrations.md](phase-2-migrations.md)). `migrate` läuft
   im `preStart` vor dem Dienststart, es gibt also keine parallelen Schreiber; borg-Backup liegt vor.
3. **`rev`+`sha256` im Modul bumpen** und das Colmena-Flake auf `mf-next` (§6, Falle 4).

Offen: **3.8** braucht F5, **4.3** braucht F4, **2.7** braucht F15, **5.4** braucht F13.

## 10. Arbeitsregeln (haben sich bewährt, bitte beibehalten)

1. **Kleine, thematisch geschlossene Commits.** Ein Commit = ein Planpunkt. Formatierung und
   Verhaltensänderung nie im gleichen Commit.
2. **Commit-Nachrichten auf Englisch, Prosa, erklären *warum*** – nicht nur was. Ende jeder
   Nachricht: `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
3. **Kommunikation mit dem User auf Deutsch. Notizen auf Deutsch. Code-Kommentare auf Deutsch**
   (so ist der Bestand). Commit-Nachrichten Englisch.
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
- **`processes = 4` im uwsgi auf einer SQLite-Datei** ist genau das Lock-Szenario aus B13. WAL und
  `timeout` in `DATABASES['default']['OPTIONS']` wären eine kleine wirksame Härtung; der User kann
  das über die `djangoSettings`-Option des Moduls sogar ohne Modul-Änderung testen.
