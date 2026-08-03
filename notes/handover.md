# Handover – demockrazy-Modernisierung

**Für eine neue Session gedacht. Dies zuerst lesen, dann [plan.md](plan.md).**
Stand: 2026-08-03, Branch `update/modernize-2026`, 21 Commits über `master` (Basis `3074dbb`).
Arbeitsbaum ist sauber, alles committed, nichts gepusht.

---

## 1. Was du in welcher Reihenfolge liest

| Datei | Wofür |
|---|---|
| **dieses Dokument** | Orientierung, Arbeitsregeln, offene Fragen, nächster Schritt |
| [plan.md](plan.md) | Der Plan mit allen Phasen, Bug-Nummern B1–B14, Fragen F1–F15. **Das Hauptdokument.** |
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

1. **Auf heutige Standards bringen.** Phase 0, 1 und 2 (außer 2.7) sind fertig, Phase 3–5 offen.
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

**Sollwerte, an denen du merkst, dass alles in Ordnung ist:**

- `pytest` → **56 passed, 9 xfailed**
- `manage.py check` → **no issues (0 silenced)**
- `makemigrations --check` → **No changes detected**
- `ruff format --check` → alle Dateien unverändert
- `ruff check` → **genau 3 Fehler**, alle in `vote/views.py` (siehe §5)

Lokal starten (nicht mit `manage.py runserver` allein – siehe §6, Falle 3):

```bash
python3 manage.py runserver --settings=demockrazy.dev_settings
```

## 5. Was absichtlich rot ist – nicht „aufräumen"

**Drei Ruff-Befunde in `vote/views.py`** bleiben stehen, bis Phase 3 sie richtig behebt:
`F841 token_object`, `F841 choice_objects`, `RUF059 amount_redeemed_tokens`. Es sind Symptome der
Bugs, nicht Stilfragen. **Nicht mit `noqa` zudecken und nicht mit `--unsafe-fixes` wegmachen.**
Das CI-Gate für Ruff kommt erst in 5.3, wenn sie weg sind.

**Neun `xfail(strict=True)`-Tests** in [../vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py)
beschreiben das *gewünschte* Verhalten für B2, B3, B4, B6, B11, B12 und die zwei fehlenden
Unique-Constraints. Sie schlagen heute fehl. **Wenn du einen Bug behebst, wird die Suite rot** –
das ist Absicht und die Erinnerung, den Marker zu entfernen. Nicht der Marker ist das Problem.

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

1. Mail-Versand als aufrufbarer Service (`vote/services/mail.py`), nicht in `create()` eingebettet.
2. Kein SMTP im Request und **nicht in der Transaktion** – `ATOMIC_REQUESTS = True` plus
   synchrones `send_mail()` heißt heute: bei Rollback sind die Mails raus, die Tokens nicht in der
   DB (B7). `transaction.on_commit()` ist der Zwischenschritt.
3. Mail-Texte als Django-Templates statt `%`-formatierte Settings-Strings (aus 2.4 nach 3.4
   verschoben, gehört zur Service-Extraktion).
4. **Zielkonflikt, den nur der User auflösen kann (F8):** ein Batch-Modus mit Retry/Zustellstatus
   braucht „welche Adresse wurde erfolgreich zugestellt". Genau diese Zuordnung wird heute
   *absichtlich nicht* gespeichert. **Kein Modell dafür entwerfen, bevor das entschieden ist.**
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

Kleinigkeit, kein Blocker: die `type`-Spalte war in der Prod-Schema-Ausgabe abgeschnitten; aus dem
Modell folgt `varchar(20) NOT NULL`, was der frische Migrationsstand exakt reproduziert. Für letzte
Sicherheit `PRAGMA table_info(vote_poll);`.

Vor Phase 3.6 (Unique-Constraints) noch auf Prod zu prüfen:
```sql
SELECT token_string, COUNT(*) c FROM vote_token GROUP BY token_string HAVING c>1;
SELECT identifier,   COUNT(*) c FROM vote_poll  GROUP BY identifier   HAVING c>1;
```

## 9. Nächster Schritt

Der User hatte die Wahl zwischen Phase 3 und Phase 4 angeboten bekommen und noch nicht entschieden.

- **Phase 3 (empfohlen):** Forms, die sechs 500-Pfade, Mail-Service herausziehen, Models aufräumen.
  Das behebt die 9 xfail-Tests und die 3 Ruff-Befunde und ist gleichzeitig die Vorarbeit für Ziel 2.
  Nicht blockiert – nur 3.8 (Zugangsschutz) braucht F5.
- **Phase 4:** Frontend. Braucht F4.
- **2.7:** Braucht F15.

Details je Schritt stehen in [plan.md](plan.md) §7–§10.

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

## 11. Wichtige Erkenntnisse, die nicht offensichtlich sind

- **Django 4.2 → 5.2 ist für diesen Code verhaltensneutral.** In Phase 0 mit 21 Fällen auf beiden
  Versionen gegengeprüft: identische Statuscodes, Redirects, Mails, Tokenlängen. Kein
  Schema-Drift, keine neuen Deprecations. Das Risiko lag nie in der Version, sondern in den
  Altlasten.
- **Prod-Migrationshistorie ist von 2016** und hat zwei Einträge. Die eingecheckten Migrations
  reproduzieren sie namensgleich, deshalb ist `migrate` dort ein **garantierter No-Op**.
- **Das k8s-Setup (`briefwahl.mayflower.cloud`) ist abgeschaltet** und in `4e15012` entfernt.
  Bestätigt risikofrei: das Prod-Modul konsumiert keine Flake-Outputs dieses Repos, nur den
  Quelltext. Falls sich das doch als falsch erweist: `git revert 4e15012`.
- **Der Mayflower-nixpkgs-Fork existiert wegen der `mayflower.*`-NixOS-Module.** Ein Wechsel auf
  upstream nixpkgs hätte den Deploy gebrochen – der User hat mich rechtzeitig auf `mf-next`
  umgelenkt. Input bleibt `github:mayflower/nixpkgs/mf-next`.
- **`processes = 4` im uwsgi auf einer SQLite-Datei** ist genau das Lock-Szenario aus B13. WAL und
  `timeout` in `DATABASES['default']['OPTIONS']` wären eine kleine wirksame Härtung; der User kann
  das über die `djangoSettings`-Option des Moduls sogar ohne Modul-Änderung testen.
