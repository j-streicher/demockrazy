# demockrazy – Modernisierungsplan

> Arbeitsdokument für Claude. Branch: `update/modernize-2026` (von `master`, Basis-Commit `3074dbb`).
> Angelegt: 2026-08-03. Notizen-Ordner: `notes/`.

---

## 0. Ziele

| # | Ziel | Status |
|---|------|--------|
| 1 | Projekt auf heutige Standards bringen (Django, Python, Nix, CI, Frontend, Deployment) | Phase 0 + 1 ✅, k8s-Cleanup ✅ |
| 2 | Batch-Modus für Mails bauen | **Spec folgt vom User** – nur Vorarbeit leisten, siehe §8 |

**Wichtig:** Ziel 2 wird vom User später erklärt. Ziel 1 nicht so umbauen, dass Ziel 2 blockiert wird –
im Gegenteil: die Mail-Logik so herausziehen, dass ein Batch-Versand sauber andocken kann (§8).

---

## 1. Was das Projekt ist

Token-basiertes anonymes Abstimmungssystem (Django), produktiv als **`wahlcomputer.mayflower.de`**.

Flow: Jemand erstellt ohne Login eine Umfrage → System generiert pro Wähler-Mailadresse einen Token
→ Tokens gehen per Mail raus → Wähler stimmt mit Token ab → Token wird gelöscht (Anonymität)
→ Umfrage schließt automatisch, wenn alle Tokens verbraucht sind → Ergebnisse werden sichtbar.

Modelle: `Poll` (title, type, num_tokens, question_text, creator_token, identifier, is_active),
`Choice` (poll, choice_text, votes), `Token` (poll, token_string) – alle in [vote/models.py](vote/models.py).

**Deployment (Stand 2026-08-03, vom User bestätigt):**

Produktiv ist `wahlcomputer.mayflower.de`, konfiguriert über `demockrazy/local_settings.py`
(nicht im Repo, gitignored – Referenzkopie liegt beim User unter `~/Desktop/democ-settings/`).
Diese Variante überschreibt `DATABASES` **nicht** ⇒ läuft auf **SQLite** (`BASE_DIR/db.sqlite3`),
setzt `DEBUG = False`, `ALLOWED_HOSTS = ['wahlcomputer.mayflower.de']`,
SMTP über `mail.mayflower.de:25` mit STARTTLS, `VOTE_SEND_MAILS = True`.

**Das k8s-Deployment (`briefwahl.mayflower.cloud`) ist abgeschaltet.** Damit sind toter Code:
[k8s/](k8s/) (Tanka/Jsonnet, Zalando-Postgres, k8s-libsonnet 1.25), [k8s/settings.py](k8s/settings.py),
[nix/demockracy-image.nix](nix/demockracy-image.nix), [nix/nginx-image.nix](nix/nginx-image.nix),
die `dockerImages`/`uwsgi`/`django_config`-Outputs und der `argocd-nix-flakes-plugin`-Input in
[flake.nix](flake.nix), [.sops.yaml](.sops.yaml) sowie der Image-Build in
[.github/workflows/build.yml](.github/workflows/build.yml). → siehe Phase 5.

**Noch offen:** wie `wahlcomputer.mayflower.de` konkret gestartet wird (NixOS-Modul? uwsgi/gunicorn
hinter nginx? systemd? welcher User, welcher Pfad zur `db.sqlite3`?). Das bestimmt Phase 5 komplett.

---

## 2. Inventar (Stand bei Branch-Start, Commit `3074dbb`)

> Historischer Ausgangszustand – **nicht** der aktuelle. Was inzwischen erledigt ist, steht in den
> Phasen-Abschnitten; die Bug-Nummern (B1…B14) werden weiter referenziert und bleiben deshalb hier.

### Toolchain
| Komponente | Ist | Bemerkung |
|---|---|---|
| nixpkgs | `mayflower/nixpkgs` ref `mf-stable`, lock vom **2024-02-07** (nixos-23.11) | ~2,5 Jahre alt |
| Django | unpinned `ps.django` aus obigem nixpkgs → **4.2.x** | 4.2 LTS EOL April 2026 → **bereits EOL** |
| Python | `python3` aus nixpkgs 23.11 → 3.11 | System hat 3.14.4 |
| Dependency-Manifest | **keines** (kein `pyproject.toml`, kein `requirements.txt`) | nur Nix + README-Prosa |
| Linter/Formatter | keiner | |
| Tests | [vote/tests.py](vote/tests.py) ist leer | keine Testabdeckung |
| `default.nix` | Legacy `with import <nixpkgs> {}`, `stdenv.mkDerivation` als Shell-Hack | Duplikat zum Flake |
| CI | `actions/checkout@v3`, `cachix/install-nix-action@v18`, `docker/login-action` auf altem SHA | nur Build, kein Test/Lint |
| Frontend | Bootstrap 3.3.6 (2016), jQuery 2.2.4 (2016), Highcharts 4.2.5 (2016) – alle vendored | |
| Datenbank (Prod) | **SQLite**, `BASE_DIR/db.sqlite3` | + `ATOMIC_REQUESTS=True` → Lock-Risiko, siehe B13 |
| k8s / Docker / sops | k8s-libsonnet 1.25, PG 14, GHCR-Images | **toter Code** – Deployment abgeschaltet, siehe Phase 5 |

### Blocker & Bugs (nach Priorität)

**B1 – Migrations sind gitignored.**
`.gitignore:60` schließt `migrations/` aus, [vote/migrations/](vote/migrations/) enthält nur `__init__.py`.
Es gibt damit **keinen Nachweis im Repo, welches Schema in Produktion liegt**; jedes System erzeugt
sich seine Migration selbst (die [README.md](README.md) instruiert genau das: `makemigrations` vor
`migrate`). Modelländerungen sind so nicht reproduzierbar und nicht reviewbar.
**Das muss zuerst weg.** Voraussetzung: Prod-Schema + `django_migrations`-Inhalt (Phase 0.3, offen).

*Hinweis:* Der zusätzliche `makemigrations`-beim-Containerstart im uwsgi-Wrapper von
[flake.nix](flake.nix) gehörte zum abgeschalteten k8s-Deployment und fällt mit Phase 5.1 weg.

**B2 – `UnboundLocalError` in `vote()`.**
[vote/views.py](vote/views.py) – `token_string = request.POST['token']` steht *innerhalb* des `try`.
Fehlt `token` im POST, wirft es `KeyError` → der Handler greift auf das nie zugewiesene
`token_string` zu → 500 statt Fehlermeldung.

**B3 – `create()` akzeptiert GET und crasht.**
[vote/views.py](vote/views.py) greift direkt auf `request.POST[...]` zu, ohne `require_POST`.
`GET /vote/create` → `MultiValueDictKeyError` → 500. Ebenso `raise Exception('Invalid poll type')` → 500.

**B4 – Kein Auth, kein Rate-Limit auf `/vote/create`.**
Jeder im Netz kann beliebig viele Umfragen anlegen und damit **beliebig viele Mails über den
SMTP-Account von Mayflower versenden**. Offenes Mail-Relay in der Praxis.
Vor Ziel 2 (Batch-Versand) zwingend zu adressieren, sonst skaliert man den Missbrauch mit.

**B5 – Unsichere Defaults in [demockrazy/settings.py](demockrazy/settings.py).**
`DEBUG = True` und ein hardcodierter `SECRET_KEY` im öffentlichen Repo als Default.
**Produktion ist davon nicht betroffen** – `local_settings.py` setzt `DEBUG = False` und einen
eigenen `SECRET_KEY` (vom User bestätigt). Das Risiko ist also, dass ein *neues* Deployment ohne
`local_settings.py` still mit unsicheren Defaults hochkommt. Fix: sichere Defaults
(`DEBUG = False`, kein Key im Repo), Konfiguration über Environment (Phase 2.4).

*Historie: Ich hatte in Phase 0.3 zunächst „Prod läuft mit DEBUG=True" befundet – das galt für
[k8s/settings.py](k8s/settings.py) und `briefwahl.mayflower.cloud`, das inzwischen abgeschaltet ist.
Der dort beschriebene Mailadressen-Leak über die 500-Pfade ist damit nicht produktionsrelevant.*

**B13 – Produktion läuft auf SQLite.**
`local_settings.py` überschreibt `DATABASES` nicht ⇒ `django.db.backends.sqlite3`.
Zusammen mit `ATOMIC_REQUESTS = True` nimmt jeder Request eine Schreibtransaktion, und SQLite
serialisiert Writer. Wenn nach dem Einladungsversand viele gleichzeitig abstimmen, sind
`database is locked`-Fehler realistisch. Auch für Ziel 2 relevant (Batch-Versand + Statusupdates).
Optionen für §12: SQLite mit WAL + `timeout` tunen (klein, reversibel) vs. Postgres (größer).
Vorher messen, nicht raten – und klären, wie oft/wie groß Abstimmungen real sind.

**B14 – Secure-Cookie-/TLS-Flags fehlen auch im Prod-Setup.**
`VOTE_BASE_URL` ist `https://`, aber `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` und `CSRF_TRUSTED_ORIGINS` sind nicht gesetzt. → 2.7.

**B11 – `manage()` crasht bei POST ohne `token`-Feld.**
[vote/views.py](vote/views.py) – `request.POST['token']` ohne Guard → `MultiValueDictKeyError` → 500.
Gleiche Klasse wie B3, eigene Stelle.

**B12 – `ValidationError` aus `parse_mails()` wird nicht gefangen.**
Eine ungültige Mailadresse im Empfängerfeld führt zu einem 500 statt zu einer Formularmeldung –
und legt unter `DEBUG=True` die *gültigen* Adressen der Liste offen (siehe B5).

**B6 – Doppelte Mailadressen bekommen doppelte Tokens.**
`parse_mails()` dedupliziert nicht → dieselbe Person kann zweimal wählen.

**B7 – Mails werden innerhalb der Transaktion versendet.**
`ATOMIC_REQUESTS = True` + `send_mail()` synchron im Request. Bei Rollback sind die Mails schon raus,
die Tokens aber nicht in der DB. Umgekehrt blockiert ein hängender SMTP-Server den Request.
→ Kernmotivation für Ziel 2.

**B8 – Highcharts 4.2.5 ist proprietär lizenziert.**
Kein Free-/Open-Source-Lizenzmodell für kommerzielle Nutzung. Vendored in
[vote/static/highcharts-custom.js](vote/static/highcharts-custom.js) in einem MIT-Repo.
→ Durch Chart.js (MIT) oder ECharts (Apache-2.0) ersetzen. **Lizenzfrage an User weitergeben.**

**B9 – Token im URL-Query-String.**
`?token=…` landet im nginx-`access_log` (`access_log /dev/stdout` → k8s-Logs), im Referer und in
der Browser-History. Der Token ist das einzige Auth-Merkmal.

**B10 – Templating in Inline-JS.**
[vote/templates/vote/results.html](vote/templates/vote/results.html) interpoliert `choice_text`
direkt in ein JS-String-Literal. Django-Autoescaping verhindert hier zwar einen Ausbruch, mangelt
aber die Anzeige. → `json_script` verwenden.

### Kleinere Punkte
- `USE_L10N` ist seit Django 5.0 entfernt → Warnung/Fehler.
- Kein `DEFAULT_AUTO_FIELD` → Django-Warnung seit 3.2.
- `re_path` überall, wo `path()`-Converter reichen ([demockrazy/urls.py](demockrazy/urls.py), [vote/urls.py](vote/urls.py)).
- `len(Token.objects.filter(...))` statt `.count()` in `Poll.get_amount_used_unused()`.
- `mk_token()`/`mk_identifier()` rekursiv statt Schleife (theoretischer Stack-Overflow).
- `manage.py` ohne den modernen `try/except ImportError`-Block.
- nginx-Image serviced `vote/static` direkt aus dem Source-Tree – kein `collectstatic`,
  keine gehashten Dateinamen, kein Cache-Busting.
- README empfiehlt `pip3 install --user django==2.2.27`.
- Templates: `<th>…</td>`-Mismatch in `results.html`; Bootstrap-3-Markup durchgehend.
- Keine `LOGGING`-Konfiguration, keine Health-/Readiness-Probe im Deployment.
- Kein `HttpResponseNotAllowed`-Handling, kein `SECURE_*`/HSTS/`CSRF_COOKIE_SECURE` in Prod-Settings.

---

## 3. Arbeitsregeln für mich

1. **Kleine, thematisch geschlossene Commits.** Ein Commit = ein Punkt aus dem Plan.
2. **Tests vor Refactoring.** Phase 1 schreibt Tests gegen das *aktuelle* Verhalten, damit die
   Umbauten in Phase 3+ verifizierbar sind. Kein Refactoring auf ungetestetem Code.
3. **Verhalten erhalten, außer wo explizit als Bug markiert.** Keine stillschweigenden
   Feature-Änderungen (z. B. Mail-Texte, Token-Längen, URL-Struktur).
4. **URLs stabil halten.** Es existieren verschickte Mails mit `?token=…`-Links auf bestehende
   Polls. `/vote/<identifier>/…` darf sich nicht ändern; Migration von B9 nur additiv.
5. **Keine Prod-Deployment-Schritte ohne Rückfrage.** k8s/Jsonnet/CI-Änderungen vorbereiten,
   aber Rollout ist Sache des Users.
6. **Versionsnummern nie aus dem Gedächtnis setzen** – immer gegen nixpkgs / PyPI verifizieren
   (Phase 0, Schritt 0.1). Das gilt für Django, Python, nixpkgs-Release, k8s-libsonnet, Actions.
7. **Nach jeder Phase:** `ruff check`, `pytest`, `manage.py check --deploy`, `nix build` – und den
   Fortschritt hier im Plan abhaken.
8. **Bei Unklarheit im Plan notieren**, in §9 sammeln, weiterarbeiten an dem, was nicht davon abhängt.

---

## 4. Phase 0 – Baseline ✅ ABGESCHLOSSEN 2026-08-03

**Volle Ergebnisse: [notes/phase-0-baseline.md](notes/phase-0-baseline.md)** – hier die Kurzfassung.

- [x] **0.1 Versionslage verifiziert.** Ist: Python 3.11.6 / Django 4.2.9. `mf-stable`-HEAD (Juni 2026)
      bringt nur Django 4.2.28 → **immer noch EOL**. Django 5.2.16 gibt es erst ab `nixos-26.05`
      (dort auch Python 3.13.14, PG 17.10). → F2 entschieden: **Django 5.2 LTS**. F3 bleibt offen.
- [x] **0.2 Läuft.** Beide Docker-Images bauen fehlerfrei. 21-Fall-Funktionsprobe
      ([notes/baseline_probe.py](notes/baseline_probe.py)) auf 4.2.9 **und** 5.2.16 gefahren:
      **Verhalten identisch**, kein Schema-Drift, keine neuen Deprecations. Das Django-Upgrade ist
      damit verhaltensneutral – das Risiko steckt in den Altlasten, nicht in der Version.
- [x] **0.3 Prod-Zustand: `DEBUG=True` bestätigt.** [k8s/settings.py](k8s/settings.py) überschreibt
      `DEBUG` nicht. Zusammen mit den 500-Pfaden ⇒ von außen auslösbare Django-Debug-Fehlerseiten,
      die **Wähler-Mailadressen** preisgeben (Passwörter/`SECRET_KEY` cleanst Django zuverlässig).
      → **Hotfix vorziehen, §4a.** Offen (braucht Cluster-Zugang): laufendes Image-Tag,
      Prod-Schema-Stand, Inhalt von `django_migrations`.
- [x] **0.4 Schema-Snapshot** in [notes/baseline-schema.sql](notes/baseline-schema.sql).
      Nebenbefund: kein `UNIQUE` auf `vote_token.token_string`, kein Index auf `vote_poll.identifier`.

## 4a. ~~Hotfix `DEBUG=False`~~ – **entfällt**

Ursprünglich als vorgezogener Hotfix geplant, weil Prod scheinbar mit `DEBUG=True` lief. Nach
Klärung des tatsächlichen Deployments (2026-08-03): Prod setzt `DEBUG = False` in
`local_settings.py`. **Kein Hotfix nötig, kein kritischer Pfad.** Die sicheren Defaults im Repo
kommen regulär in Phase 2.4, die 500-Pfade in Phase 3.

## 5. Phase 1 – Fundament ✅ ABGESCHLOSSEN 2026-08-03

- [x] **1.1 `pyproject.toml`** – Metadaten, `django>=5.2,<6.0`, Extras `postgres` (psycopg nur
      relevant, falls B13 auf Postgres führt) und `dev`. Nix bleibt Source of Truth für den Build.
- [x] **1.2 Ruff** konfiguriert (line-length 100, `F,E,W,I,UP,B,C4,DJ,DTZ,RUF`), safe autofixes +
      `ruff format` als eigener Commit. `demockrazy/settings.py` hat `per-file-ignores` für `E501`
      (deutsche Prosa in den Mail-Texten) und `F403` (der `local_settings`-Import) – beide fallen
      mit 2.4 weg. `notes/` ist ausgenommen.
      **3 Befunde bleiben absichtlich rot:** 2× `F841` + 1× `RUF059` in
      [vote/views.py](vote/views.py) – Symptome der Bugs, die Phase 3 richtig behebt. CI-Gate: 5.3.
- [x] **1.3 pytest + pytest-django** über `pyproject.toml`, eigene
      [demockrazy/test_settings.py](demockrazy/test_settings.py) (locmem-Mails, In-Memory-SQLite,
      unabhängig von `local_settings.py`). **Abweichung vom Plan:** die Suite ist pytest-only statt
      auch `manage.py test`-kompatibel – `xfail`-Marker funktionieren im unittest-Runner nicht, und
      die Bug-Spezifikation in 1.4 ist mir wichtiger als zwei Runner.
- [x] **1.4 Testsuite** in [vote/tests/](vote/tests/): **56 Tests grün, 9 xfailed.**
      Models, alle sechs Views, Anonymitätsgarantien, plus ein URL-Form-Test als Absicherung von
      Regel 4. Die 9 Bugs stehen in [vote/tests/test_known_bugs.py](vote/tests/test_known_bugs.py)
      als `xfail(strict=True)` – sie beschreiben das Soll-Verhalten und machen die Suite rot, sobald
      Phase 3 sie fixt (= Erinnerung, den Marker zu entfernen).
- [x] **1.5 `default.nix`** entfernt.
- [x] **1.6 `flake.nix`** – Input auf **`github:mayflower/nixpkgs/mf-next`** (vom User empfohlen,
      ist auf `26.05.20260724`; `mf-stable` ist so gut wie abgelöst). Liefert Python 3.13.13,
      Django 5.2.15, ruff, pytest, pytest-django. devShell um `tanka`/`jsonnet-bundler`/`sops`
      erleichtert. Damit ist Django 5.2 **schon in Phase 1 aktiv**, nicht erst in 2.3.

### Befund aus 1.4, der 2.1 dringlicher macht

Die Suite läuft nur, weil `vote/migrations/0001_initial.py` **lokal** existiert. Auf einem frischen
Clone fallen **49 von 56 Tests** um, weil `migrations/` gitignored ist. Die Tests sind also für
niemanden außer mir nutzbar und in CI wertlos, solange 2.1 nicht erledigt ist.
⇒ **2.1 ist der nächste Schritt** und braucht F12 (Prod-Schema).

## 6. Phase 2 – Django-Upgrade & Konfiguration

- [ ] **2.1 Migrations einchecken (B1).** `migrations/` aus [.gitignore](.gitignore) entfernen,
      `0001_initial` generieren, gegen [notes/baseline-schema.sql](notes/baseline-schema.sql) **und die
      Prod-SQLite-DB** verifizieren, committen. Deploy-Pfad festlegen und dokumentieren:
      `migrate` (wenn `django_migrations` den Eintrag schon hat) vs. `--fake-initial` (wenn nicht).
      **Blockiert durch den offenen Prod-Schema-Stand aus 0.3.**
- [ ] **2.2 `makemigrations` aus dem Deploy-Weg nehmen (B1).** Fällt größtenteils mit 5.1 weg
      (uwsgi-Wrapper im Flake). Verbleibt: die [README.md](README.md) instruiert `makemigrations` als
      Setup-Schritt – das muss zu `migrate` werden.
- [ ] **2.3 Django auf 5.2.16 / Python 3.13** heben, in Nix **explizit pinnen** statt `ps.django`.
      Deprecations abarbeiten: `USE_L10N` raus, `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`.
      Laut Phase 0.2 verhaltensneutral – trotzdem die Testsuite aus 1.4 als Gegenprobe.
- [ ] **2.4 Settings-Layout aufräumen.** Sichere Defaults im Repo (`DEBUG = False`, kein `SECRET_KEY`),
      Konfiguration über Environment (B5). `local_settings.py` bleibt als Prod-Mechanismus erhalten
      (Regel 3 – nicht ohne Not umstellen, Prod hängt daran), aber die Defaults dürfen nicht mehr
      unsicher sein. **`local_settings.py.example` ins Repo**, damit der Prod-Mechanismus dokumentiert
      ist – Inhalt aus `~/Desktop/democ-settings/`, ohne Secrets.
      Mail-Templates in echte Django-Templates ziehen (Vorarbeit für §11).
- [ ] **2.5 `manage.py`** auf aktuelles Boilerplate.
- [ ] **2.6 `python_files`/Deprecation-Warnungen** als Fehler in pytest schalten, damit die nächste
      Django-Version nicht wieder überrascht.
- [ ] **2.7 `manage.py check --deploy`** grün bekommen: `SECURE_HSTS_*`, `SECURE_SSL_REDIRECT`,
      `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `X_FRAME_OPTIONS` in den Prod-Settings.
      `LOGGING` auf strukturiertes stdout-Logging.

## 7. Phase 3 – Code-Modernisierung

- [ ] **3.1 `vote/forms.py`** einführen: `PollCreateForm` mit `EmailField`-Validierung,
      Choices-Parsing, Dedup der Mailadressen (B6). Ersetzt `parse_mails`/`parse_choices` und
      den direkten `request.POST`-Zugriff.
- [ ] **3.2 `create()`** auf Form + `require_POST`/GET-Handling umbauen (B3); Fehler als
      Formularfehler rendern statt 500.
- [ ] **3.3 `vote()`** entzerren (B2): `token_string` vor dem `try` lesen, Fehlerpfade explizit.
- [ ] **3.4 Mail-Versand in `vote/services/mail.py` herausziehen (B7).** Reine Funktionen, keine
      Request-Abhängigkeit, kein SMTP innerhalb der Transaktion → `transaction.on_commit()`.
      **Das ist die Schnittstelle, an der Ziel 2 andockt** (§8).
- [ ] **3.5 Poll-Erstellung in `vote/services/polls.py`**: Tokens/Choices bulk-erzeugen
      (`bulk_create` statt Save-Loop).
- [ ] **3.6 Models aufräumen:** `.count()` statt `len()`, Schleife statt Rekursion in
      `mk_token`/`mk_identifier`, `UniqueConstraint` auf `Token.token_string` und
      `Poll.identifier`, `db_index` wo sinnvoll, `POLL_TYPES` als `TextChoices`,
      `get_absolute_url()`. → eigene Migration.
- [ ] **3.7 `re_path` → `path`** mit `<slug:poll_identifier>`/Custom-Converter; URLs identisch halten (Regel 4).
- [ ] **3.8 Rate-Limit / Zugangsschutz für `create` (B4).** Optionen für §9:
      (a) Django-Auth + Login-Zwang, (b) Shared Secret / Invite-Code, (c) IP-Rate-Limit,
      (d) Deckel auf Empfängerzahl pro Poll. **Entscheidung braucht den User.**

## 8. Phase 4 – Frontend

- [ ] **4.1 Bootstrap 3.3.6 → 5.3.x** (vendored, kein CDN – CSP-freundlich): `base.html`,
      Navbar, `form-group` → `mb-3`, `nav-pills`/`badge` in
      [token_state.html](vote/templates/vote/token_state.html), Alerts.
- [ ] **4.2 jQuery entfernen** – Bootstrap 5 braucht es nicht, die einzige Nutzung ist der
      Chart-Init in `results.html`.
- [ ] **4.3 Highcharts ersetzen (B8)** durch Chart.js (MIT) oder ECharts (Apache-2.0),
      Daten über `{{ ...|json_script }}` statt Inline-Interpolation (B10).
- [ ] **4.4 `collectstatic` + Whitenoise** mit gehashten Dateinamen (Cache-Busting).
      Whitenoise ist bei der Nicht-Container-Deployform ohnehin die einfachere Variante –
      Details hängen an 5.2.
- [ ] **4.5 Template-Kleinkram:** `<th>/</td>`-Mismatch, `lang="de"` wo die Texte deutsch sind,
      doppelt eingebundenes `bootstrap.css` in `base.html`.

## 9. Phase 5 – Deployment & CI

**Komplett neu geschnitten**, nachdem sich das k8s-Deployment als abgeschaltet erwiesen hat.
Aus „k8s modernisieren" wird „k8s entfernen" – das streicht die aufwändigsten Punkte des alten
Plans (k8s-libsonnet-Bump, PG14→17-Migration mit Wartungsfenster, sops-Keys, Deployment-Härtung)
und ersetzt sie durch Aufräumen.

- [ ] **5.1 Toten Deployment-Code entfernen.** **Braucht ein Go vom User** (§12 F10).
      Betrifft: [k8s/](k8s/), [nix/](nix/) (beide Image-Definitionen), [.sops.yaml](.sops.yaml),
      die Flake-Outputs `dockerImages`/`packages.uwsgi`/`packages.django_config`/`apps` und den
      `argocd-nix-flakes-plugin`-Input, sowie den Image-Build-Job in
      [.github/workflows/build.yml](.github/workflows/build.yml).
      Nebeneffekt: erledigt B1s `makemigrations`-beim-Start und die uwsgi-Frage (alte 5.2) von selbst.
      Git-History bleibt – wiederherstellbar, falls das k8s-Setup je zurückkommt.
- [ ] **5.2 Prod-Deployment dokumentieren und dann erst anfassen.** Wie läuft
      `wahlcomputer.mayflower.de` konkret? (§12 F11) Ohne diese Antwort kann ich nicht sagen, ob der
      Django-/Python-Bump aus Phase 2 dort überhaupt greift – ein NixOS-Modul, ein manuelles
      `pip install` oder ein systemd-Service mit eigenem venv verhalten sich völlig verschieden.
      **Das ist der wichtigste offene Punkt für Ziel 1**: ein Upgrade, das nicht deploybar ist, ist keins.
- [ ] **5.3 CI neu aufbauen:** ohne Image-Build bleibt ein schlanker Workflow für
      `ruff check` + `pytest` + `nix flake check`. `actions/checkout` und `install-nix-action` auf
      aktuelle Majors.
- [ ] **5.4 SQLite-Betrieb absichern (B13),** abhängig von 5.2: WAL-Modus und `timeout` über
      `DATABASES['default']['OPTIONS']`, Backup-Strategie für die `db.sqlite3` klären
      (liegt sie auf einem Volume? wird sie gesichert?). Postgres nur, wenn die Last es hergibt –
      vorher messen.
- [ ] **5.5 `/healthz`-Endpoint** – klein, nützlich unabhängig von der Deployment-Form.

## 10. Phase 6 – Dokumentation

- [ ] **6.1 README neu:** Setup über `nix develop`/`direnv`, korrekte Django-Version,
      Test- und Lint-Befehle, Deployment-Überblick, Erklärung des Token-/Anonymitätsmodells.
- [ ] **6.2 `CLAUDE.md`** mit den Projekt-Konventionen (Layout, Commit-Stil, Testbefehle),
      damit künftige Sessions nicht wieder von vorn inventarisieren.
- [ ] **6.3 `notes/`** aktuell halten: Entscheidungen + Ergebnisse aus 0.1/0.3 hier eintragen.

---

## 11. Vorarbeit für Ziel 2 (Batch-Modus für Mails)

Spec kommt vom User. Bis dahin **nicht spekulativ implementieren**, aber Phase 3 so bauen, dass
folgende Punkte gegeben sind – sie sind für jede Variante von „Batch“ nötig:

1. **Mail-Versand ist eine aufrufbare Service-Funktion**, nicht in `create()` eingebettet (3.4).
2. **Kein SMTP im Request-Zyklus / nicht in der Transaktion** – `transaction.on_commit()` als
   Zwischenschritt (B7).
3. **Mail-Inhalte als Django-Templates** statt `%`-formatierte Settings-Strings (2.4) – sonst wird
   jede Batch-Variante mit Personalisierung unschön.
4. **Zustand pro Empfänger ist modellierbar.** Aktuell ist die Zuordnung Mail→Token *absichtlich*
   nicht persistiert (Anonymität!). Ein Batch-Modus mit Retry/Status braucht aber „welche Adresse
   wurde erfolgreich zugestellt“. **Das ist ein Konflikt mit dem Anonymitätsversprechen und muss
   mit dem User geklärt werden**, bevor irgendein Modell entsteht.
5. **Missbrauchsschutz vor Skalierung** (B4) – ein Batch-Versender ohne Zugangsschutz ist ein
   Spam-Werkzeug.
6. Offen zu klären, sobald die Spec da ist: Queue/Worker (Celery? `django-tasks`? DB-Queue +
   Management-Command + CronJob?), Rate-Limits des SMTP-Anbieters, Bounce-Handling,
   Idempotenz/Retry, Fortschrittsanzeige für den Poll-Ersteller.

---

## 12. Offene Fragen an den User

| # | Frage | Blockiert |
|---|-------|-----------|
| ~~F1~~ | ~~Läuft Prod mit `DEBUG=True`?~~ → **nein.** Der Befund galt für das abgeschaltete k8s-Deployment; Prod setzt `DEBUG = False`. Kein Hotfix nötig. | – |
| ~~F2~~ | ~~Django-Zielversion?~~ → **5.2.16 LTS**, das ist auch die einzige, die nixpkgs liefert | – |
| ~~F3~~ | ~~nixpkgs-Input?~~ → **`github:NixOS/nixpkgs/nixos-26.05`** | – |
| ~~F6~~ | ~~uwsgi oder gunicorn?~~ → entfällt, der uwsgi-Wrapper gehörte zum k8s-Deployment. Neu als Teil von F11. | – |
| ~~F7~~ | ~~Postgres 14→17-Wartungsfenster?~~ → entfällt, Prod läuft auf SQLite. Ersetzt durch B13/5.4. | – |
| ~~F9~~ | ~~`.sops.yaml`-Keys?~~ → entfällt, fällt mit 5.1 weg. | – |
| **F10** | Darf der tote Deployment-Code raus ([k8s/](k8s/), [nix/](nix/), [.sops.yaml](.sops.yaml), Image-Outputs im Flake, Image-Build in der CI)? Git-History bleibt, also reversibel. | 5.1, 1.6 |
| **F11** | **Wie wird `wahlcomputer.mayflower.de` konkret deployt und gestartet?** NixOS-Modul, systemd + venv, uwsgi/gunicorn hinter nginx, manuelles `git pull`? Wo liegt die `db.sqlite3`, wird sie gesichert? Wer darf ausrollen? | 5.2, 5.4, und faktisch das ganze Deploy-Ende von Ziel 1 |
| **F12** | Prod-Schema-Stand: Ausgabe von `.schema vote_*` + `django_migrations` aus der Prod-SQLite (Kommando steht in [notes/phase-0-baseline.md](notes/phase-0-baseline.md)) | 2.1 |
| F4 | Highcharts-Lizenz: existiert eine kommerzielle Lizenz, oder ersetzen? (B8) | 4.3 |
| F5 | Zugangsschutz für Poll-Erstellung – welche Variante? (B4/3.8) | 3.8, Ziel 2 |
| F8 | Anonymität vs. Zustellstatus pro Empfänger – wie weit darf Ziel 2 das aufweichen? (§11.4) | Ziel 2 |
| F13 | Wie groß sind Abstimmungen real (Empfänger pro Poll, parallele Polls)? Entscheidet SQLite-Tuning vs. Postgres (B13) und die Batch-Größen für Ziel 2. | 5.4, Ziel 2 |

---

## 13. Reihenfolge / Abhängigkeiten

```
Phase 0 (Baseline, Prod-Fakten)  ✅
  └─ Phase 1 (Tooling + Tests)          ← Sicherheitsnetz, alles Weitere hängt daran
       ├─ Phase 2 (Migrations, Django, Settings)
       │    │   2.1 braucht F12 (Prod-Schema)
       │    ├─ Phase 3 (Code, Forms, Mail-Service) ← liefert die Schnittstelle für Ziel 2
       │    │    └─ ZIEL 2 (Batch-Mails, nach Spec)
       │    └─ Phase 5 (k8s-Cleanup, CI, SQLite)   ← 5.1 braucht F10, 5.2 braucht F11
       └─ Phase 4 (Frontend, unabhängig parallelisierbar)
Phase 6 (Docs) laufend mitschreiben
```

**Nächster Schritt:** Phase 0.1 + 0.2 – Versionslage verifizieren und prüfen, ob das Projekt lokal
überhaupt startet. Erst danach etwas anfassen.
