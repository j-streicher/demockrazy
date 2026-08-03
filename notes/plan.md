# demockrazy – Modernisierungsplan

> Arbeitsdokument für Claude. Branch: `update/modernize-2026` (von `master`, Basis-Commit `3074dbb`).
> Angelegt: 2026-08-03. Notizen-Ordner: `notes/`.

---

## 0. Ziele

| # | Ziel | Status |
|---|------|--------|
| 1 | Projekt auf heutige Standards bringen (Django, Python, Nix, CI, Frontend, Deployment) | offen |
| 2 | Batch-Modus für Mails bauen | **Spec folgt vom User** – nur Vorarbeit leisten, siehe §8 |

**Wichtig:** Ziel 2 wird vom User später erklärt. Ziel 1 nicht so umbauen, dass Ziel 2 blockiert wird –
im Gegenteil: die Mail-Logik so herausziehen, dass ein Batch-Versand sauber andocken kann (§8).

---

## 1. Was das Projekt ist

Token-basiertes anonymes Abstimmungssystem (Django), produktiv als `briefwahl.mayflower.cloud`.

Flow: Jemand erstellt ohne Login eine Umfrage → System generiert pro Wähler-Mailadresse einen Token
→ Tokens gehen per Mail raus → Wähler stimmt mit Token ab → Token wird gelöscht (Anonymität)
→ Umfrage schließt automatisch, wenn alle Tokens verbraucht sind → Ergebnisse werden sichtbar.

Modelle: `Poll` (title, type, num_tokens, question_text, creator_token, identifier, is_active),
`Choice` (poll, choice_text, votes), `Token` (poll, token_string) – alle in [vote/models.py](vote/models.py).

Deployment: Nix Flake → 2 Docker-Images (uwsgi + nginx) → GHCR → Tanka/Jsonnet → k8s,
Postgres via Zalando postgres-operator, Secrets via sops.

---

## 2. Ist-Zustand / Inventar

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
| k8s | k8s-libsonnet **1.25**, PostgreSQL **14** | PG14 EOL Nov 2026 |

### Blocker & Bugs (nach Priorität)

**B1 – Migrations sind gitignored, `makemigrations` läuft beim Container-Start.**
`.gitignore:60` schließt `migrations/` aus, [vote/migrations/](vote/migrations/) enthält nur `__init__.py`.
Der uwsgi-Wrapper in [flake.nix](flake.nix) führt bei jedem Start `makemigrations && migrate` aus –
gegen einen Read-only-Nix-Store-Pfad, und generiert das Schema jedes Mal neu.
Funktioniert nur, weil die Generierung deterministisch ist. Jede Modelländerung ist damit
unkontrolliert deploybar und nicht reproduzierbar. **Das muss zuerst weg.**

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

**B5 – Hardcodierter `SECRET_KEY`, `DEBUG = True` als Default.**
[demockrazy/settings.py](demockrazy/settings.py) – der Key steht im öffentlichen Git-Repo.
Prod überschreibt beides über [k8s/settings.py](k8s/settings.py) … `DEBUG` aber **nicht**.
→ Prüfen, ob Prod aktuell mit `DEBUG=True` läuft. Wenn ja: kritisch, sofort fixen.

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

## 4. Phase 0 – Baseline (keine funktionalen Änderungen)

- [ ] **0.1 Versionslage verifizieren.** Aktuelles nixpkgs-Stable-Release ermitteln; prüfen ob
      `mayflower/nixpkgs#mf-stable` noch der richtige Input ist oder auf `NixOS/nixpkgs` gewechselt
      werden soll. Django-Zielversion aus PyPI/nixpkgs bestimmen (Erwartung: **5.2 LTS**;
      6.x nur wenn alle Deps mitspielen). Python-Version passend dazu. Ergebnisse hier eintragen.
- [ ] **0.2 Läuft es überhaupt?** `nix develop`, `manage.py migrate`, `manage.py runserver`,
      Happy Path manuell durchklicken (Poll erstellen mit `VOTE_SEND_MAILS=False` → Konsolen-Mail →
      abstimmen → Ergebnis). Abweichungen notieren.
- [ ] **0.3 Prod-Zustand klären.** Läuft Prod mit `DEBUG=True` (B5)? Welches Image-Tag läuft?
      Schema-Stand der Prod-DB (`\d+` auf `vote_*`) → Referenz für die eingecheckten Migrations.
- [ ] **0.4 Snapshot des generierten Schemas** ablegen unter `notes/baseline-schema.sql`, damit die
      eingecheckte `0001_initial` gegen Prod verifizierbar ist.

## 5. Phase 1 – Fundament: Dependencies, Tooling, Tests

- [ ] **1.1 `pyproject.toml`** anlegen: Projekt-Metadaten, explizit gepinnte Dependencies
      (`django`, `psycopg[binary]`), Dev-Extras (`pytest`, `pytest-django`, `ruff`).
      Nix bleibt Source of Truth für den Build, aber die Deps müssen *lesbar deklariert* sein.
- [ ] **1.2 Ruff** konfigurieren (`pyproject.toml`: lint + format, `DJ`-Regeln aktiv), einmal über
      das Repo laufen lassen, Formatierung als **eigener Commit** (Diff-Rauschen isolieren).
- [ ] **1.3 pytest + pytest-django** einrichten, `manage.py test` bleibt funktionsfähig.
- [ ] **1.4 Tests gegen Ist-Verhalten** in `vote/tests/`:
      Poll-Erstellung, Mail-Generierung (`locmem`-Backend), Abstimmen (simple + multiple),
      Token-Verbrauch/Löschung, Auto-Close bei 0 Tokens, Manage-Token, Ergebnis-Redirects,
      `get_amount_used_unused()` in allen drei Fällen. **Auch die Bugs B2/B3/B6 als
      `xfail`-Tests** festhalten → werden in Phase 3 zu grünen Tests.
- [ ] **1.5 `default.nix`** entfernen (oder auf flake-compat reduzieren) – Duplikat zum Flake.
- [ ] **1.6 `flake.nix`**: `devShells` um `ruff`, `pytest` erweitern; `nixpkgs`-Input aktualisieren
      (Ergebnis aus 0.1); `flake.lock` neu.

## 6. Phase 2 – Django-Upgrade & Konfiguration

- [ ] **2.1 Migrations einchecken (B1).** `migrations/` aus [.gitignore](.gitignore) entfernen,
      `0001_initial` generieren, gegen `notes/baseline-schema.sql` und die Prod-DB verifizieren,
      committen. `--fake-initial` als Deploy-Pfad für die bestehende Prod-DB dokumentieren.
- [ ] **2.2 `makemigrations` aus dem Container-Start entfernen (B1).** In [flake.nix](flake.nix)
      nur noch `migrate`. Mittelfristig: als k8s-Init-Container / Job statt im uwsgi-Wrapper.
- [ ] **2.3 Django auf Zielversion** (aus 0.1) heben, in Nix **explizit pinnen** statt `ps.django`.
      Deprecations abarbeiten: `USE_L10N` raus, `DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'`.
- [ ] **2.4 Settings-Layout aufräumen.** `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS`/DB/SMTP durchgehend
      aus dem Environment (B5), sicherer Default = `DEBUG=False`. Der `local_settings`-Import-Hack
      und die Prosa-Konstanten (`VOTE_*_MAIL_TEXT`) sollen bleiben können, aber
      [k8s/settings.py](k8s/settings.py) darf nicht mehr die einzige Stelle sein, die Prod absichert.
      Mail-Templates mittelfristig in echte Django-Templates ziehen (Vorarbeit für §8).
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
- [ ] **4.4 `collectstatic` + Whitenoise** oder gehashte Static-Files im nginx-Image;
      [nix/nginx-image.nix](nix/nginx-image.nix) auf das `collectstatic`-Output zeigen lassen.
- [ ] **4.5 Template-Kleinkram:** `<th>/</td>`-Mismatch, `lang="de"` wo die Texte deutsch sind,
      doppelt eingebundenes `bootstrap.css` in `base.html`.

## 9. Phase 5 – Deployment, CI, k8s

- [ ] **5.1 CI erweitern:** Job für `ruff check` + `pytest` **vor** dem Image-Build.
      `actions/checkout` und `install-nix-action` auf aktuelle Majors, `docker/login-action`-SHA
      aktualisieren (SHA-Pinning beibehalten). Nix-Cache (magic-nix-cache o. Ä.) erwägen.
- [ ] **5.2 uwsgi vs. gunicorn entscheiden.** Der aktuelle uwsgi-Wrapper ist ein Shell-Skript mit
      `pushd` in den Nix-Store und einem `master = <store-path>`-Feld, das nach einem Copy-Paste-Fehler
      aussieht (`master` erwartet einen Bool). Gunicorn wäre deutlich einfacher zu paketieren,
      erfordert aber `uwsgi_pass` → `proxy_pass` in [nix/nginx-image.nix](nix/nginx-image.nix).
      → §10, Entscheidung des Users.
- [ ] **5.3 k8s-libsonnet 1.25 → aktuelle Version**, `jsonnetfile.lock.json` neu, `tanka eval` prüfen.
- [ ] **5.4 PostgreSQL 14 → 16/17** in [k8s/environments/default/main.jsonnet](k8s/environments/default/main.jsonnet)
      (PG14 EOL Nov 2026). **Braucht ein Migrationsfenster + Backup → nur vorbereiten, nicht ausrollen.**
- [ ] **5.5 Deployment härten:** `resources` (requests/limits), `livenessProbe`/`readinessProbe`
      (dafür einen `/healthz`-Endpoint), `securityContext` (non-root, read-only rootfs),
      `strategy` für Zero-Downtime. Migrate als Init-Container/Job (aus 2.2).
- [ ] **5.6 `.sops.yaml`-Keys** vom User bestätigen lassen – die fünf PGP-Fingerprints sind
      vermutlich teilweise veraltet. **Nicht selbst anfassen.**

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
| F1 | Läuft Prod aktuell mit `DEBUG=True`? (B5) | 0.3 / 2.4 |
| F2 | Django **5.2 LTS** (konservativ, Support bis 2028) oder neueste Major? | 2.3 |
| F3 | nixpkgs-Input: bei `mayflower/nixpkgs#mf-stable` bleiben oder auf upstream `nixos-XX.YY`? | 1.6 |
| F4 | Highcharts-Lizenz: existiert eine kommerzielle Lizenz, oder ersetzen? (B8) | 4.3 |
| F5 | Zugangsschutz für Poll-Erstellung – welche Variante? (B4/3.8) | 3.8, Ziel 2 |
| F6 | uwsgi behalten oder auf gunicorn wechseln? (5.2) | 5.2 |
| F7 | Postgres-Upgrade 14→17: gibt es ein Wartungsfenster / wer fährt es? (5.4) | 5.4 |
| F8 | Anonymität vs. Zustellstatus pro Empfänger – wie weit darf Ziel 2 das aufweichen? (§11.4) | Ziel 2 |
| F9 | Darf `.sops.yaml` / der Key-Kreis angepasst werden, und von wem? | 5.6 |

---

## 13. Reihenfolge / Abhängigkeiten

```
Phase 0 (Baseline, Prod-Fakten)
  └─ Phase 1 (Tooling + Tests)          ← Sicherheitsnetz, alles Weitere hängt daran
       ├─ Phase 2 (Migrations, Django, Settings)   ← B1 zuerst, das ist der Deploy-Blocker
       │    ├─ Phase 3 (Code, Forms, Mail-Service) ← liefert die Schnittstelle für Ziel 2
       │    │    └─ ZIEL 2 (Batch-Mails, nach Spec)
       │    └─ Phase 5 (CI, k8s, Deployment)
       └─ Phase 4 (Frontend, unabhängig parallelisierbar)
Phase 6 (Docs) laufend mitschreiben
```

**Nächster Schritt:** Phase 0.1 + 0.2 – Versionslage verifizieren und prüfen, ob das Projekt lokal
überhaupt startet. Erst danach etwas anfassen.
