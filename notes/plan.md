# demockrazy – Modernisierungsplan

> Arbeitsdokument für Claude. Branch: `update/modernize-2026` (von `master`, Basis-Commit `3074dbb`).
> Angelegt: 2026-08-03. Notizen-Ordner: `notes/`.

---

## 0. Ziele

| # | Ziel | Status |
|---|------|--------|
| 1 | Projekt auf heutige Standards bringen (Django, Python, Nix, CI, Frontend, Deployment) | Phase 0, 1 ✅ · Phase 2 bis auf 2.7 ✅ · k8s-Cleanup ✅ · Phase 3 bis 3.6 ✅ · CI ✅ · offen: 3.7, 3.8, 4, 5.4, 5.5 |
| 2 | Batch-Modus für Mails bauen | **Spec folgt vom User** – nur Vorarbeit leisten, siehe §11 |

**Wichtig:** Ziel 2 wird vom User später erklärt. Ziel 1 nicht so umbauen, dass Ziel 2 blockiert wird –
im Gegenteil: die Mail-Logik so herausziehen, dass ein Batch-Versand sauber andocken kann (§11).

---

## 1. Was das Projekt ist

Token-basiertes anonymes Abstimmungssystem (Django), produktiv als **`wahlcomputer.mayflower.de`**.

Flow: Jemand erstellt ohne Login eine Umfrage → System generiert pro Wähler-Mailadresse einen Token
→ Tokens gehen per Mail raus → Wähler stimmt mit Token ab → Token wird gelöscht (Anonymität)
→ Umfrage schließt automatisch, wenn alle Tokens verbraucht sind → Ergebnisse werden sichtbar.

Modelle: `Poll` (title, type, num_tokens, question_text, creator_token, identifier, is_active),
`Choice` (poll, choice_text, votes), `Token` (poll, token_string) – alle in [vote/models.py](../vote/models.py).

**Deployment (Stand 2026-08-03, aus der Colmena-Node-Config des Users):**

Produktiv ist `wahlcomputer.mayflower.de`, ausgerollt per **colmena** (Zielhost
`wahlcomputer.dmz.muc.mayflower.zone`, Tags `ci-build`/`vm`). Die App wird von einem
**eigenen NixOS-Modul `mayflower.demockrazy`** gestartet – das liegt **außerhalb dieses Repos** und
erklärt, warum es den Mayflower-nixpkgs-Fork mit seinen `mayflower.*`-Modulen gibt.

**Vollständige Analyse des Moduls: [notes/deployment.md](deployment.md).** Kurzfassung:

- App läuft **aus dem Nix-Store** unter uwsgi (4 Prozesse), `ProtectSystem = "full"`,
  nginx via `uwsgi_pass unix:/run/demockrazy/uwsgi.socket`.
- `DJANGO_SETTINGS_MODULE=demockrazy_config` – ein **vom Modul generiertes** Settings-Modul, das
  `from demockrazy.settings import *` macht und danach überschreibt. `local_settings.py` ist in
  Produktion **nicht** im Spiel; die Datei unter `~/Desktop/democ-settings/` war veraltet
  (sie nennt `mail.mayflower.de:25`, der Node konfiguriert `smtp.mayflower.de:587`).
- **`BASE_DIR` ist der Store-Pfad, nicht `/var/lib/demockrazy`** – DB und `STATIC_ROOT` werden
  *absolut* dorthin umgebogen, weil der Store read-only ist.
- **`DEBUG = False` ist bestätigt** (explizit im generierten Modul) → F14 beantwortet.
  Ebenso `CSRF_COOKIE_SECURE`/`SESSION_COOKIE_SECURE` und `LOGGING`.
- **Backups laufen:** borg onsite 03:00 + offsite 04:00 auf `/var/lib/demockrazy` → 5.4 beantwortet.
- `preStart` ruft `migrate` und `collectstatic --noinput` – kein `makemigrations`.
- **Löschcommit `4e15012` ist bestätigt risikofrei:** das Modul konsumiert keine Flake-Outputs
  dieses Repos, nur den Quelltext.

⚠️ **Wie das Upgrade Prod erreicht – zwei Änderungen im User-Repo, nicht hier:**
1. Das Modul pinnt `rev = 3074dbb` (= Basis-Commit dieses Branches) per `fetchFromGitHub`.
   Ohne `rev`+`sha256`-Bump ändert sich in Produktion **nichts**.
2. Die **Django-Version kommt aus der nixpkgs des Colmena-Flakes**, nicht aus diesem Repo
   (`pkgs.python3Packages.django`): `mf-stable` → 4.2.28 (EOL), `mf-next` → 5.2.15.
   `pyproject.toml` dokumentiert die Anforderung, erzwingt sie nicht.

**Das k8s-Deployment (`briefwahl.mayflower.cloud`) ist abgeschaltet.** War toter Code und ist
**in `4e15012` entfernt**: `k8s/` (Tanka/Jsonnet, Zalando-Postgres, k8s-libsonnet 1.25) inkl.
`k8s/settings.py`, `nix/demockracy-image.nix`, `nix/nginx-image.nix`, die Flake-Outputs
`dockerImages`/`packages.uwsgi`/`packages.django_config`/`apps`, der
`argocd-nix-flakes-plugin`-Input und der GHCR-Image-Build in `.github/workflows/build.yml`.
Wiederherstellbar über `git revert 4e15012`.

---

## 2. Inventar (Stand bei Branch-Start, Commit `3074dbb`)

> Historischer Ausgangszustand – **nicht** der aktuelle. Was inzwischen erledigt ist, steht in den
> Phasen-Abschnitten; die Bug-Nummern (B1…B15) werden weiter referenziert und bleiben deshalb hier.
> B15 ist später dazugekommen und deshalb kein Befund vom Branch-Start.

### Toolchain
| Komponente | Ist | Bemerkung |
|---|---|---|
| nixpkgs | `mayflower/nixpkgs` ref `mf-stable`, lock vom **2024-02-07** (nixos-23.11) | ~2,5 Jahre alt |
| Django | unpinned `ps.django` aus obigem nixpkgs → **4.2.x** | 4.2 LTS EOL April 2026 → **bereits EOL** |
| Python | `python3` aus nixpkgs 23.11 → 3.11 | System hat 3.14.4 |
| Dependency-Manifest | **keines** (kein `pyproject.toml`, kein `requirements.txt`) | nur Nix + README-Prosa |
| Linter/Formatter | keiner | |
| Tests | `vote/tests.py` enthielt nur einen Kommentar | keine Testabdeckung |
| `default.nix` | Legacy `with import <nixpkgs> {}`, `stdenv.mkDerivation` als Shell-Hack | Duplikat zum Flake |
| CI | `actions/checkout@v3`, `cachix/install-nix-action@v18`, `docker/login-action` auf altem SHA | nur Build, kein Test/Lint |
| Frontend | Bootstrap 3.3.6 (2016), jQuery 2.2.4 (2016), Highcharts 4.2.5 (2016) – alle vendored | |
| Datenbank (Prod) | **SQLite**, `/var/lib/demockrazy/db.sqlite3` | + `ATOMIC_REQUESTS=True` → Lock-Risiko, siehe B13 |
| k8s / Docker / sops | k8s-libsonnet 1.25, PG 14, GHCR-Images | **toter Code** – Deployment abgeschaltet, siehe Phase 5 |

### Bug-Register

| # | Kurz | Status |
|---|---|---|
| B1 | Migrations gitignored | ✅ **behoben** in 2.1 |
| B2 | `UnboundLocalError` in `vote()` | ✅ **behoben** in 3.3 |
| B3 | `create()` crasht bei GET / ungültigem Typ | ✅ **behoben** in 3.2 |
| B4 | Kein Auth/Rate-Limit auf `/vote/create` | offen → 3.8, **braucht F5** |
| B5 | Unsichere Settings-Defaults | ✅ **behoben** in 2.4 |
| B6 | Doppelte Adressen → doppelte Tokens | ✅ **behoben** in 3.1/3.2 |
| B7 | Mailversand innerhalb der Transaktion | ✅ **behoben** in 3.4 |
| B8 | Highcharts proprietär lizenziert | offen → 4.3, **braucht F4** |
| B9 | Token im URL-Query-String | offen, Entscheidung nötig |
| B10 | Templating in Inline-JS | offen → 4.3 |
| B11 | `manage()` crasht ohne `token`-Feld | ✅ **behoben** in 3.2 |
| B12 | `ValidationError` ungefangen | ✅ **behoben** in 3.1/3.2 |
| B13 | Prod läuft auf SQLite (Lock-Risiko) | offen → 5.4, **braucht F13** |
| B14 | TLS-Hardening unvollständig | offen → 2.7, **braucht F15** |
| B15 | `choice`-Wert ohne Zahl → 500 | ✅ **behoben** in 3.3 (neu gefunden) |

Alle als `xfail(strict=True)` spezifiziert in
[vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py); B2, B3, B6, B11 und B12 stehen
dort inzwischen ohne Marker als Regressionstests. **Offen ist von den 500-Pfaden nur noch B4**
(braucht F5) sowie die zwei fehlenden Unique-Constraints. B15 kam erst in 3.3 dazu und war sofort
behoben, hatte also nie einen Marker.


**B1 – Migrations sind gitignored.**
`.gitignore:60` schließt `migrations/` aus, [vote/migrations/](../vote/migrations/) enthält nur `__init__.py`.
Es gibt damit **keinen Nachweis im Repo, welches Schema in Produktion liegt**; jedes System erzeugt
sich seine Migration selbst (die [README.md](../README.md) instruiert genau das: `makemigrations` vor
`migrate`). Modelländerungen sind so nicht reproduzierbar und nicht reviewbar.
✅ **Behoben in 2.1** – siehe [notes/phase-2-migrations.md](phase-2-migrations.md).
Der zusätzliche `makemigrations`-beim-Containerstart im uwsgi-Wrapper des Flakes gehörte zum
k8s-Deployment und ist mit `4e15012` weg.

**B2 – `UnboundLocalError` in `vote()`.**
[vote/views.py](../vote/views.py) – `token_string = request.POST['token']` steht *innerhalb* des `try`.
Fehlt `token` im POST, wirft es `KeyError` → der Handler greift auf das nie zugewiesene
`token_string` zu → 500 statt Fehlermeldung.

**B3 – `create()` akzeptiert GET und crasht.**
[vote/views.py](../vote/views.py) greift direkt auf `request.POST[...]` zu, ohne `require_POST`.
`GET /vote/create` → `MultiValueDictKeyError` → 500. Ebenso `raise Exception('Invalid poll type')` → 500.

**B4 – Kein Auth, kein Rate-Limit auf `/vote/create`.**
Jeder im Netz kann beliebig viele Umfragen anlegen und damit **beliebig viele Mails über den
SMTP-Account von Mayflower versenden**. Offenes Mail-Relay in der Praxis.
Vor Ziel 2 (Batch-Versand) zwingend zu adressieren, sonst skaliert man den Missbrauch mit.

**B5 – Unsichere Defaults in [demockrazy/settings.py](../demockrazy/settings.py).**
`DEBUG = True` und ein hardcodierter `SECRET_KEY` im öffentlichen Repo als Default.
Produktion war nie betroffen – das generierte `demockrazy_config` setzt beides.
Das Risiko war, dass ein *neues* Deployment still mit unsicheren Defaults hochkommt.
✅ **Behoben in 2.4.**

*Historie, zweimal korrigiert: In Phase 0.3 hatte ich „Prod läuft mit DEBUG=True" befundet – das
galt für `k8s/settings.py` und das abgeschaltete `briefwahl.mayflower.cloud`. Danach nahm ich an,
`local_settings.py` setze `DEBUG = False`; tatsächlich tut das das NixOS-Modul (§1). Der
Mailadressen-Leak über die 500-Pfade war also nie produktionsrelevant.*

**B13 – Produktion läuft auf SQLite.**
`local_settings.py` überschreibt `DATABASES` nicht ⇒ `django.db.backends.sqlite3`.
Zusammen mit `ATOMIC_REQUESTS = True` nimmt jeder Request eine Schreibtransaktion, und SQLite
serialisiert Writer. Wenn nach dem Einladungsversand viele gleichzeitig abstimmen, sind
`database is locked`-Fehler realistisch. Auch für Ziel 2 relevant (Batch-Versand + Statusupdates).
Optionen für §12: SQLite mit WAL + `timeout` tunen (klein, reversibel) vs. Postgres (größer).
Vorher messen, nicht raten – und klären, wie oft/wie groß Abstimmungen real sind.

**B14 – TLS-Hardening-Settings fehlen in Prod.** *(korrigiert 2026-08-03)*
`SESSION_COOKIE_SECURE` und `CSRF_COOKIE_SECURE` **sind** gesetzt – das Modul macht das über
`secureCookies` (Default `true`). Der Befund war insoweit zu pauschal.
Es fehlen: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `CSRF_TRUSTED_ORIGINS` und
`SECURE_PROXY_SSL_HEADER`. **Nicht blind einschalten** – TLS endet vorgelagert, ohne Proxy-Header
gibt `SECURE_SSL_REDIRECT` eine Redirect-Schleife. Gehört ins Modul, nicht in die Repo-Defaults.
→ 2.7, blockiert durch F15. Details in [notes/deployment.md](deployment.md).

**B11 – `manage()` crasht bei POST ohne `token`-Feld.**
[vote/views.py](../vote/views.py) – `request.POST['token']` ohne Guard → `MultiValueDictKeyError` → 500.
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
[vote/static/highcharts-custom.js](../vote/static/highcharts-custom.js) in einem MIT-Repo.
→ Durch Chart.js (MIT) oder ECharts (Apache-2.0) ersetzen. **Lizenzfrage an User weitergeben.**

**B9 – Token im URL-Query-String.**
`?token=…` landet im nginx-Access-Log des Hosts, im Referer und in der Browser-History.
Der Token ist das einzige Auth-Merkmal. Eine Änderung wäre nur **additiv** möglich (Regel 4:
es sind Mails mit solchen Links unterwegs) – z. B. Token per POST/Session einlösen und den
GET-Pfad weiter unterstützen. Braucht eine Entscheidung, ob der Aufwand lohnt.

**B15 – `choice`-Wert ohne Zahl ergibt einen 500.** *(neu gefunden in 3.3)*
`poll.choice_set.get(pk=request.POST["choice"])` wirft bei einem nicht-numerischen Wert
(`"abc"`, `""`) einen `ValueError`, nicht `Choice.DoesNotExist` – und den fing niemand.
Auslösbar von jedem, der einen gültigen Token hat, mit einem handgebauten POST. Kein Datenleck
(Prod läuft mit `DEBUG=False`), aber ein 500 im Log statt einer Fehlermeldung.
Gemessen, nicht vermutet: `"abc"`, `""` und `"1; DROP TABLE"` → 500, `"9"*20` → 200 mit
Fehlermeldung (das ist eine Zahl, nur keine existierende ID).
✅ **Behoben in 3.3** zusammen mit B2, weil es dieselbe Klasse ist: ungeprüfter POST-Zugriff.

**B10 – Templating in Inline-JS.**
[vote/templates/vote/results.html](../vote/templates/vote/results.html) interpoliert `choice_text`
direkt in ein JS-String-Literal. Django-Autoescaping verhindert hier zwar einen Ausbruch, mangelt
aber die Anzeige. → `json_script` verwenden.

### Kleinere Punkte

Erledigt: `USE_L10N` (2.4) · `DEFAULT_AUTO_FIELD` (2.4) · `manage.py`-Boilerplate (2.5) ·
README/`pip3 install django==2.2.27` (2.2) · `LOGGING` (setzt das Prod-Modul) ·
Static-Handling aus dem Source-Tree (mit den Docker-Images in `4e15012` weg).

Noch offen:
- `re_path` überall, wo `path()`-Converter reichen ([demockrazy/urls.py](../demockrazy/urls.py),
  [vote/urls.py](../vote/urls.py)) → 3.7.
- `len(Token.objects.filter(...))` statt `.count()` in `Poll.get_amount_used_unused()` → 3.6.
- `mk_token()`/`mk_identifier()` rekursiv statt Schleife (theoretischer Stack-Overflow) → 3.6.
- Kein Cache-Busting für Static Files → 4.4.
- Templates: `<th>…</td>`-Mismatch in `results.html`; Bootstrap-3-Markup durchgehend → 4.1/4.5.
- Kein `HttpResponseNotAllowed`-Handling → 3.2.
- Kein `/healthz` → 5.5.

---

## 3. Arbeitsregeln für mich

1. **Kleine, thematisch geschlossene Commits.** Ein Commit = ein Punkt aus dem Plan.
2. **Tests vor Refactoring.** Phase 1 schreibt Tests gegen das *aktuelle* Verhalten, damit die
   Umbauten in Phase 3+ verifizierbar sind. Kein Refactoring auf ungetestetem Code.
3. **Verhalten erhalten, außer wo explizit als Bug markiert.** Keine stillschweigenden
   Feature-Änderungen (z. B. Mail-Texte, Token-Längen, URL-Struktur).
4. **URLs stabil halten.** Es existieren verschickte Mails mit `?token=…`-Links auf bestehende
   Polls. `/vote/<identifier>/…` darf sich nicht ändern; Migration von B9 nur additiv.
5. **Keine Prod-Deployment-Schritte ohne Rückfrage.** Das NixOS-Modul liegt außerhalb dieses
   Repos; Änderungen daran benennen, aber nicht selbst machen. Rollout ist Sache des Users.
6. **Versionsnummern nie aus dem Gedächtnis setzen** – immer gegen nixpkgs / PyPI verifizieren
   (Phase 0, Schritt 0.1). Das gilt für Django, Python, nixpkgs-Release, k8s-libsonnet, Actions.
7. **Nach jeder Änderung:** `pytest` · `manage.py check` · `makemigrations --check --dry-run` ·
   `ruff format --check .` · `ruff check .` – Sollwerte in [handover.md](handover.md) §4.
   Danach den Fortschritt hier im Plan abhaken.
8. **Bei Unklarheit im Plan notieren**, in §12 sammeln, weiterarbeiten an dem, was nicht davon abhängt.

---

## 4. Phase 0 – Baseline ✅ ABGESCHLOSSEN 2026-08-03

**Volle Ergebnisse: [notes/phase-0-baseline.md](phase-0-baseline.md)** – hier die Kurzfassung.

- [x] **0.1 Versionslage verifiziert.** Ist: Python 3.11.6 / Django 4.2.9. `mf-stable`-HEAD (Juni 2026)
      bringt nur Django 4.2.28 → **immer noch EOL**. Django 5.2.16 gibt es erst ab `nixos-26.05`
      (dort auch Python 3.13.14, PG 17.10). → F2 entschieden: **Django 5.2 LTS**.
      F3 wurde danach zugunsten von `mf-next` entschieden (siehe 1.6).
- [x] **0.2 Läuft.** Beide Docker-Images bauen fehlerfrei. 21-Fall-Funktionsprobe
      ([notes/baseline_probe.py](baseline_probe.py)) auf 4.2.9 **und** 5.2.16 gefahren:
      **Verhalten identisch**, kein Schema-Drift, keine neuen Deprecations. Das Django-Upgrade ist
      damit verhaltensneutral – das Risiko steckt in den Altlasten, nicht in der Version.
- [x] **0.3 Prod-Zustand.** ⚠️ **Dieser Befund galt dem falschen Deployment** – siehe Korrektur
      unter §1. Damals: `k8s/settings.py` überschreibt
      `DEBUG` nicht. Zusammen mit den 500-Pfaden ⇒ von außen auslösbare Django-Debug-Fehlerseiten,
      die **Wähler-Mailadressen** preisgeben (Passwörter/`SECRET_KEY` cleanst Django zuverlässig).
      Damals als Hotfix eingeplant (§4a) – hat sich mit der Deployment-Klärung erledigt.
- [x] **0.4 Schema-Snapshot** in [notes/baseline-schema.sql](baseline-schema.sql).
      Nebenbefund: kein `UNIQUE` auf `vote_token.token_string`, kein Index auf `vote_poll.identifier`.

## 4a. ~~Hotfix `DEBUG=False`~~ – **entfällt**

Ursprünglich als vorgezogener Hotfix geplant, weil Prod scheinbar mit `DEBUG=True` lief – das galt
aber dem abgeschalteten k8s-Deployment. Tatsächlich setzt das vom NixOS-Modul generierte
`demockrazy_config` **`DEBUG = False`** (§1). **Kein Hotfix nötig, kein kritischer Pfad.**
Die sicheren Defaults im Repo sind mit 2.4 erledigt, die 500-Pfade folgen in Phase 3.

## 5. Phase 1 – Fundament ✅ ABGESCHLOSSEN 2026-08-03

- [x] **1.1 `pyproject.toml`** – Metadaten, `django>=5.2,<6.0`, Extras `postgres` (psycopg nur
      relevant, falls B13 auf Postgres führt) und `dev`. Nix bleibt Source of Truth für den Build.
- [x] **1.2 Ruff** konfiguriert (line-length 100, `F,E,W,I,UP,B,C4,DJ,DTZ,RUF`), safe autofixes +
      `ruff format` als eigener Commit. `demockrazy/settings.py` hat `per-file-ignores` für `E501`
      (deutsche Prosa in den Mail-Texten) und `F403` (der `local_settings`-Import). `notes/` ist
      ausgenommen. *Nachtrag: beide bestehen nach 2.4 weiter* – `E501` fällt erst mit 3.4 weg
      (Mail-Texte werden Templates), `F403` bleibt, solange der `local_settings`-Import existiert.
      **3 Befunde bleiben absichtlich rot:** 2× `F841` + 1× `RUF059` in
      [vote/views.py](../vote/views.py) – Symptome der Bugs, die Phase 3 richtig behebt.
      *Nachtrag: alle drei sind mit 3.2 und 3.3 weggefallen, keiner per `noqa`. Das CI-Gate steht
      seit 5.3.*
- [x] **1.3 pytest + pytest-django** über `pyproject.toml`, eigene
      [demockrazy/test_settings.py](../demockrazy/test_settings.py) (locmem-Mails, In-Memory-SQLite,
      unabhängig von `local_settings.py`). **Abweichung vom Plan:** die Suite ist pytest-only statt
      auch `manage.py test`-kompatibel – `xfail`-Marker funktionieren im unittest-Runner nicht, und
      die Bug-Spezifikation in 1.4 ist mir wichtiger als zwei Runner.
- [x] **1.4 Testsuite** in [vote/tests/](../vote/tests/): **56 Tests grün, 9 xfailed** *(Stand bei
      1.4; aktueller Sollwert steht in [handover.md](handover.md) §4)*.
      Models, alle sechs Views, Anonymitätsgarantien, plus ein URL-Form-Test als Absicherung von
      Regel 4. Die 9 Bugs stehen in [vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py)
      als `xfail(strict=True)` – sie beschreiben das Soll-Verhalten und machen die Suite rot, sobald
      Phase 3 sie fixt (= Erinnerung, den Marker zu entfernen).
- [x] **1.5 `default.nix`** entfernt.
- [x] **1.6 `flake.nix`** – Input auf **`github:mayflower/nixpkgs/mf-next`** (vom User empfohlen,
      ist auf `26.05.20260724`; `mf-stable` ist so gut wie abgelöst). Liefert Python 3.13.13,
      Django 5.2.15, ruff, pytest, pytest-django. devShell um `tanka`/`jsonnet-bundler`/`sops`
      erleichtert. Damit ist Django 5.2 **schon in Phase 1 aktiv**, nicht erst in 2.3.

### Befund aus 1.4 ✅ abgearbeitet

Die Suite lief zunächst nur, weil `vote/migrations/0001_initial.py` **lokal** existierte – auf einem
frischen Clone fielen **49 von 56 Tests** um, weil `migrations/` gitignored war. Damit waren die
Tests für niemanden außer mir nutzbar und in CI wertlos. **Behoben in 2.1**, auf einem frischen
`git clone` verifiziert.

## 6. Phase 2 – Django-Upgrade & Konfiguration

- [x] **2.1 Migrations einchecken (B1)** ✅ – **Details: [notes/phase-2-migrations.md](phase-2-migrations.md)**
      Prod hatte **zwei** angewendete Migrations (`0001_initial` 2016-06-09,
      `0002_auto_20160701_2022` 2016-07-01). Deshalb **beide unter ihren Originalnamen
      rekonstruiert** statt eine zusammengefasste `0001_initial`. Beweis der Korrektheit: die
      Spaltenreihenfolge von `vote_poll` stimmt danach exakt mit Prod überein
      (`… is_active, num_tokens, type`), was eine zusammengefasste Migration nicht leistet.
      `makemigrations --check` sauber. **Deploy: `migrate` ist ein garantierter No-Op,
      kein `--fake-initial`.** Frischer Clone verifiziert: 56 grün, 9 xfailed.
      Restrisiko dokumentiert: Prod-FKs ohne `DEFERRABLE`, alte Index-Namen → relevant für 3.6.
- [x] **2.2 `makemigrations` aus dem Deploy-Weg** ✅ – im Flake mit 5.1 entfallen, in der
      [README.md](../README.md) beide Vorkommen ersetzt. Die README war ohnehin durch das Löschen von
      `default.nix` kaputt (`nix-shell` gibt es nicht mehr), daher gleich neu geschrieben – das
      verschiebt 6.1 nach vorn.
- [x] **2.3 Django 5.2 / Python 3.13** ✅ – bereits mit 1.6 erledigt (mf-next: Django 5.2.15,
      Python 3.13.13), Django in Nix nicht mehr unpinned. Die zugehörigen Deprecations
      (`USE_L10N`, `DEFAULT_AUTO_FIELD`) sind in 2.4 mitgemacht.
- [x] **2.4 Settings-Defaults sicher gemacht** ✅
      `DEBUG = False` als Default, kein `SECRET_KEY` im Repo, Konfiguration über `DEMOCKRAZY_*`.
      `USE_L10N` raus, `DEFAULT_AUTO_FIELD = AutoField` (**nicht** `BigAutoField` – das hätte eine
      `AlterField`-Migration erzeugt, die auf SQLite alle drei Tabellen neu schreibt, für null
      Gewinn). Damit ist `manage.py check` **komplett sauber**, ohne Migrations-Drift.
      Der `print("No local settings found..")` ist weg (lief bei jedem Prod-Start ins Syslog).
      Neu: [demockrazy/dev_settings.py](../demockrazy/dev_settings.py), weil `DEBUG=False` als Default
      `runserver` blockiert – analog zu `test_settings.py`, in der README dokumentiert.
      **Gegen Prod verifiziert:** das generierte `demockrazy_config` nachgebaut und dagegen geladen –
      `SECRET_KEY` kommt aus der Datei, alle Overrides greifen, `check` sauber.
      **Verschoben nach 3.4:** die Mail-Texte in echte Django-Templates ziehen. Sie sind kein
      Settings-Thema, und der Umbau gehört zur Extraktion des Mail-Service – sonst fasse ich
      `views.py` zweimal an. Die Testsuite deckt die Mailinhalte ab, der Move bleibt damit sicher.
- [x] **2.5 `manage.py`** ✅ auf aktuelles Boilerplate, `setdefault` beibehalten (Prod setzt
      `DJANGO_SETTINGS_MODULE=demockrazy_config` im systemd-Service).
- [x] **2.6 Deprecation-Warnungen als Fehler** ✅ – schon mit 1.1 in `pyproject.toml` erledigt
      (`filterwarnings = error::DeprecationWarning, error::PendingDeprecationWarning`).
- [ ] **2.7 `check --deploy` grün bekommen – BLOCKIERT durch F15.**
      Bereits erledigt bzw. gegenstandslos: `DEBUG`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`
      (setzt das Modul), `LOGGING` (setzt das Modul), `ALLOWED_HOSTS`.
      Offen: `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `CSRF_TRUSTED_ORIGINS`,
      `SECURE_PROXY_SSL_HEADER`. **Nicht anfassen, bis F15 geklärt ist** – TLS endet vorgelagert,
      ohne Proxy-Header erzeugt `SECURE_SSL_REDIRECT` eine Redirect-Schleife. Diese Werte gehören
      ins NixOS-Modul (oder über dessen `djangoSettings`-Option), nicht in die Repo-Defaults.

## 7. Phase 3 – Code-Modernisierung

- [x] **3.1 `vote/forms.py`** ✅ – `PollCreateForm` mit `EmailField`-Validierung, Choices-Parsing
      über `parse_lines()` und Dedup der Mailadressen (B6). Feldnamen identisch zu den
      `name`-Attributen von [index.html](../vote/templates/vote/index.html), damit die Vorlage
      unverändert bleibt (Regel 4). `cleaned_data` liefert `choices`/`voter_mails` als Listen.
      **Abweichung vom Plan:** das Formular ist *noch nicht verdrahtet* – der Umbau von `create()`
      steckt komplett in 3.2. Sobald die View das Formular benutzt, kippen B3, B6 und B12
      gleichzeitig von `xfail` auf grün; das gehört in denselben Commit wie die 500-Pfade, sonst
      ist die Suite zwischendurch halb umgestellt und nicht mehr lesbar. Bis dahin deckt
      [vote/tests/test_forms.py](../vote/tests/test_forms.py) das Formular ab (**+35 Tests**).
      **Drei bewusste Verschärfungen** (Eingaben, die die View bisher annahm):
      alle Felder sind Pflicht (leerer Titel / leere Choice- oder Empfängerliste ergaben eine
      Umfrage, über die nicht abgestimmt werden kann, bzw. einen 500 beim SMTP-Aufruf);
      Adressprüfung über Djangos Validator statt der Heuristik „genau ein `@`, dahinter ein Punkt"
      (die z. B. `a b@example.org` durchließ); `title` auf die Spaltenbreite 200 begrenzt.
      Dedup case-insensitiv über die ganze Adresse, erste Schreibweise gewinnt – Begründung im
      Code. **Falls der User eine davon nicht will, ist das vor 3.2 zu klären.**
- [x] **3.2 `create()` auf das Formular umgebaut** ✅ – `parse_mails`/`parse_choices` sind weg,
      damit sind **B3, B6, B12** behoben; zusätzlich **B11** (`manage()` liest den Token jetzt mit
      `.get()`, eigener Commit). Vier `xfail`-Marker entfernt, die Tests bleiben als
      Regressionstests stehen.
      **Kein `require_POST`:** ein GET auf `/vote/create` rendert das Formular statt eines 405.
      Der Endpunkt ist der Sache nach POST-only, aber ein 405 ist für einen Menschen aus der
      Browser-History eine Sackgasse.
      [index.html](../vote/templates/vote/index.html) behält sein handgeschriebenes
      Bootstrap-3-Markup (4.1 ersetzt es ohnehin) und bekommt nur, was das Formular braucht:
      Fehlerlisten pro Feld und die Eingaben zurück ins Feld – ohne Letzteres kostet ein Tippfehler
      in Adresse 200 die ganze Liste. Bei ungültiger Eingabe entsteht nichts und es geht **keine**
      Mail raus, auch nicht an den Ersteller.
      Nebeneffekt: einer der drei roten Ruff-Befunde ist weg (`F841 choice_objects`), **2 bleiben**
      (`poll()`, `vote()`) → 3.3.
- [x] **3.3 `vote()` entzerrt** ✅ (B2) – `token_string` wird vor dem `try` mit `.get()` gelesen,
      die Token-Abfrage ist aus dem großen `try` heraus in die Query gewandert (`poll=poll` fasst
      „unbekannter Token" und „Token einer anderen Umfrage" zu einem Pfad zusammen; beide hießen
      schon vorher `invalid token.`). Das Zählen sind zwei benannte Helfer, jede `except`-Klausel
      deckt genau einen Fall ab. Der `atomic()`-Block bleibt um das Zählen – das ist, was die
      Teilstimme bei unvollständigem `multiple_choice` zurücknimmt.
      **Neu gefunden und gleich mitbehoben: B15** (nicht-numerischer `choice`-Wert → 500).
      `poll()`: die unbenutzte Token-Abfrage ist ein `exists()`-Check. **Absichtlich weiter ohne
      `poll=poll`** – ein fremder Token wird auf der Seite nicht angemeckert und fällt erst beim
      Abschicken auf; das ist eine Anzeigefrage, keine Lücke, und eine Änderung würde ohne Gewinn
      das Verhalten verschieben. Ggf. in Phase 4 als UX-Punkt aufgreifen.
      **`ruff check` ist damit erstmals sauber** → Voraussetzung für 5.3 erfüllt.
- [x] **3.4 Mail-Versand in [vote/services/mail.py](../vote/services/mail.py) herausgezogen** ✅ (B7)
      – reine Funktionen ohne Request-Abhängigkeit, Versand über `transaction.on_commit()`.
      Die Nachrichten werden **vor** dem Commit fertig gerendert, damit der Callback ohne
      Datenbankzugriff auskommt. **Das ist die Schnittstelle, an der Ziel 2 andockt** (§11):
      `poll_created_messages()` baut die Liste, `deliver()` verschickt sie – ein Batch-Versender
      ersetzt genau das zweite.
      **Mail-Texte sind jetzt Templates** unter `vote/templates/vote/mail/` (der aus 2.4
      verschobene Punkt); damit fällt das `E501`-per-file-ignore für `settings.py` weg.
      In `settings.py` bleiben nur `VOTE_MAIL_FROM`, `VOTE_BASE_URL`, `VOTE_SEND_MAILS`.
      **Wortlaut byteweise erhalten**, festgenagelt in
      [test_mail_service.py](../vote/tests/test_mail_service.py) mit den alten Settings-Strings als
      Literalen: inklusive führender/abschließender Leerzeile (deshalb enden die Templates ohne
      Zeilenumbruch) und des überzähligen `"` nach „Deutsche Bahn". **Autoescaping in den
      Mail-Templates aus** – sonst würde aus `Bier & Brezn` beim Empfänger `Bier &amp; Brezn`.
      **Drei benannte Verhaltensänderungen:**
      (a) die Zustellfehler-Liste auf der Bestätigungsseite ist weg – der Versand läuft nach dem
      Commit, die Seite ist dann schon gerendert; Fehler gehen ins Log.
      (b) Der Logaufruf enthält **bewusst weder Empfängeradresse noch Umfragekennung** (F8); der
      Text einer SMTP-Exception kann die Adresse aber selbst enthalten – mit F8 zu bewerten.
      (c) Wähler bekommen die Tokens in Listenreihenfolge statt rückwärts (`pop()` → `zip()`);
      nicht beobachtbar, weil Tokens zufällig sind und die Zuordnung nirgends gespeichert wird.
      **Testinfrastruktur:** `django_db` committet nie, also feuern `on_commit`-Callbacks nicht.
      Die `create_poll`-Fixture führt sie über `django_capture_on_commit_callbacks` aus; die zwei
      Tests, die *keine* Mail erwarten, ebenfalls – sonst wären sie inhaltsleer. Dazu ein Test mit
      echter Transaktion als Beleg, dass der Pfad auch ohne diese Hilfe läuft.
- [x] **3.5 Poll-Erstellung in [vote/services/polls.py](../vote/services/polls.py)** ✅ –
      `bulk_create` statt Save-Schleife, ohne Request- und Formular-Abhängigkeit, damit ein
      Management-Command (Ziel 2) sie genauso aufrufen kann. `transaction.atomic` drauf: im Request
      redundant (`ATOMIC_REQUESTS`, dort nur ein Savepoint), aber sonst wäre der erste Aufruf von
      außerhalb nicht abgesichert.
      **Gemessen auf der Test-DB, 2 Choices + 200 Empfänger: 404 → 206 Queries, INSERTs 203 → 3.**
      Was bleibt, sind SELECTs – **einer pro Token** aus der Kollisionsprüfung in `mk_token()`.
      → **Aufgabe für 3.6:** mit dem `UniqueConstraint` auf `token_string` ist die Vorabprüfung
      überflüssig; ohne sie fällt dieselbe Umfrage auf **6 Queries**. Das ist der eigentliche
      Gewinn des Constraints, nicht nur die Integrität.
      Zwei Annahmen geprüft statt vermutet und per Test festgenagelt: `bulk_create` liefert auf
      diesem SQLite die PKs mit zurück (RETURNING), und die Choice-Reihenfolge überlebt.
      *Nebenbefund:* die Kollisionsprüfung in `mk_token()` sieht die Geschwister eines
      `bulk_create`-Batches nicht, weil alle Objekte vor dem ersten INSERT konstruiert werden. Bei
      62^128 möglichen Tokens ist das kein praktisches Risiko, und ab 3.6 fängt es die Datenbank.
- [x] **3.6 Models aufgeräumt** ✅ – Migration `0003_model_constraints_and_choices`.
      `UniqueConstraint` auf `Token.token_string` und `Poll.identifier`; **kein zusätzliches
      `db_index`**, der Constraint bringt seinen Index mit.
      **Die Kollisionsprüfungen sind ganz weg** statt zu Schleifen umgebaut: sie sahen die
      Geschwister eines `bulk_create`-Batches nicht und konnten Eindeutigkeit prinzipiell nicht
      garantieren. Damit **fällt die Umfrage-Erstellung auf konstant 5 Statements** (200 Empfänger:
      vorher 404, nach 3.5 noch 206) – besser als die in 3.5 vorhergesagten 6, weil auch die
      `mk_identifier`-Prüfung wegfiel. Der Punkt „Rekursion → Schleife" erledigt sich damit: es gibt
      nichts mehr zu rekursieren.
      **Korrektur einer eigenen Annahme:** `UniqueConstraint` erzeugt auf SQLite **kein**
      `CREATE UNIQUE INDEX`. SQLite kann keinen Constraint anhängen, Django **schreibt die Tabelle
      neu**. Gegen ein exaktes Prod-Abbild geprüft – Daten unversehrt, FKs konsistent,
      Spaltenreihenfolge unverändert; `vote_token` wird dabei normalisiert (FK `DEFERRABLE`,
      Index umbenannt), `vote_choice` nicht. Vollständig in
      [phase-2-migrations.md](phase-2-migrations.md). Kein Nebenläufigkeitsrisiko: `migrate` läuft
      im `preStart`, bevor der Dienst startet.
      `POLL_TYPES` → `PollType(models.TextChoices)`; Werte unverändert (Spaltenwerte im Bestand,
      per Test festgehalten), das Formular zieht seine Choices daraus, die View vergleicht gegen das
      Enum-Mitglied. `get_amount_used_unused()` zählt und summiert in der Datenbank
      (`Sum()` → `None` bei einer Umfrage ohne Choices, eigener Test). `get_absolute_url()` ist kein
      Zierrat – die Wähler-Mail baut ihren Link darauf.
      **Die letzten zwei `xfail`-Marker sind weg**, offen ist nur noch B4 (braucht F5).
      Ein `per-file-ignore` dazugekommen: `RUF012` für `vote/models.py`, weil eine Liste Djangos
      dokumentierte Schnittstelle für `Meta.constraints` ist.
- [ ] **3.7 `re_path` → `path`** mit `<slug:poll_identifier>`/Custom-Converter; URLs identisch halten (Regel 4).
- [ ] **3.8 Rate-Limit / Zugangsschutz für `create` (B4).** Optionen für §12:
      (a) Django-Auth + Login-Zwang, (b) Shared Secret / Invite-Code, (c) IP-Rate-Limit,
      (d) Deckel auf Empfängerzahl pro Poll. **Entscheidung braucht den User.**

## 8. Phase 4 – Frontend

- [ ] **4.1 Bootstrap 3.3.6 → 5.3.x** (vendored, kein CDN – CSP-freundlich): `base.html`,
      Navbar, `form-group` → `mb-3`, `nav-pills`/`badge` in
      [token_state.html](../vote/templates/vote/token_state.html), Alerts.
- [ ] **4.2 jQuery entfernen** – Bootstrap 5 braucht es nicht, die einzige Nutzung ist der
      Chart-Init in `results.html`.
- [ ] **4.3 Highcharts ersetzen (B8)** durch Chart.js (MIT) oder ECharts (Apache-2.0),
      Daten über `{{ ...|json_script }}` statt Inline-Interpolation (B10).
- [ ] **4.4 Cache-Busting für Static Files.** **Kein Whitenoise** – nginx serviced `/static` schon
      direkt aus `/var/lib/demockrazy/static` (siehe §1), das soll so bleiben. Stattdessen
      `STORAGES["staticfiles"]` auf `ManifestStaticFilesStorage` für gehashte Dateinamen.
      `collectstatic --noinput` läuft laut Modul bei **jedem** Service-Start, die Umstellung ist
      damit gefahrlos.
- [ ] **4.5 Template-Kleinkram:** `<th>/</td>`-Mismatch, `lang="de"` wo die Texte deutsch sind,
      doppelt eingebundenes `bootstrap.css` in `base.html`. Neu dazu: die handgeschriebenen
      `<input>`/`<textarea>` in [index.html](../vote/templates/vote/index.html) tragen kein
      `aria-describedby` auf die Fehlerliste, die Django daneben rendert (mit 3.2 entstanden, weil
      das Markup bewusst nicht auf `{{ form.<feld> }}` umgestellt wurde).

## 9. Phase 5 – Deployment & CI

Ursprünglich „k8s modernisieren", nach der Klärung des Deployments zu „k8s entfernen" geworden –
das strich die aufwändigsten Punkte (k8s-libsonnet-Bump, PG14→17 mit Wartungsfenster, sops-Keys,
Deployment-Härtung). **5.1 und 5.2 sind erledigt**, offen bleiben CI, SQLite-Härtung und `/healthz`.

- [x] **5.1 Toten Deployment-Code entfernt** ✅ in `4e15012` (549 Zeilen): `k8s/`, `nix/`,
      `.sops.yaml`, die Flake-Outputs `dockerImages`/`packages.uwsgi`/`packages.django_config`/`apps`,
      der `argocd-nix-flakes-plugin`-Input und der GHCR-Image-Build-Workflow.
      **Risikofrei bestätigt** nach Einsicht ins NixOS-Modul: es konsumiert keine Flake-Outputs
      dieses Repos, nur den Quelltext ([deployment.md](deployment.md)).
      Nebeneffekt: erledigt B1s `makemigrations`-beim-Start und die alte uwsgi-vs-gunicorn-Frage.
      Rückweg: `git revert 4e15012`.
- [x] **5.2 Prod-Deployment verstanden** ✅ – Analyse in [deployment.md](deployment.md).
      **Ergebnis, das im Repo nicht lösbar ist:** das Modul pinnt `rev = 3074dbb`, und die
      Django-Version kommt aus der nixpkgs des Colmena-Flakes. Damit das Upgrade Prod erreicht,
      muss der User `rev`+`sha256` bumpen **und** das Colmena-Flake auf `mf-next` haben.
      Beim `rev`-Bump auch `version = "2024-02-08"` im Derivation mitziehen. **Kein Rollout durch
      mich** (Regel 5) – nur benennen.
- [x] **5.3 CI neu aufgebaut** ✅ – [.github/workflows/checks.yml](../.github/workflows/checks.yml)
      fährt **genau die Verifikationsschleife aus [handover.md](handover.md) §4** plus
      `nix flake check`. Nicht nur `ruff`+`pytest`: `makemigrations --check` gehört dazu, weil
      Migrations-Drift sonst erst dem nächsten auffällt, der ein Modell anfasst.
      Versionen gegen die GitHub-API geprüft, nicht erinnert: `actions/checkout@v7` (v7.0.1,
      2026-07-20), `cachix/install-nix-action@v31` (v31.11.0, 2026-07-15). Flakes explizit
      eingeschaltet statt auf den Action-Default zu bauen.
      **Kein Binary-Cache-Schritt, gemessen statt vermutet:** Python 3.13.13, Django 5.2.15,
      pytest, pytest-django und ruff sind alle aus `cache.nixos.org` substituierbar; nur der
      `withPackages`-Symlink-Join wird gebaut (Sekunden). Ein Cachix-Account bringt hier nichts.
      **Trigger `push` auf allen Branches, kein `pull_request`:** bei einem PR aus diesem Repo hängt
      das Ergebnis am Commit und erscheint am PR; beide Trigger zusammen ergäben zwei Läufe pro
      Push. Für Fork-PRs müsste der zweite Trigger dazu.
      Der Vorgänger-Workflow baute nur die Images des abgeschalteten k8s-Deployments und ist mit
      `4e15012` entfallen – seither hatte das Repo **gar keine** CI.
- [ ] **5.4 SQLite-Betrieb absichern (B13).** WAL-Modus und `timeout` über
      `DATABASES['default']['OPTIONS']`. **Backup ist geklärt:** borg onsite 03:00 + offsite 04:00
      auf `/var/lib/demockrazy`. Verschärfend: das Modul startet **4 uwsgi-Prozesse** auf einer
      SQLite-Datei. Postgres nur, wenn die Last es hergibt – vorher messen, braucht F13.
      Testbar ohne Modul-Änderung über die `djangoSettings`-Option des Moduls.
- [ ] **5.5 `/healthz`-Endpoint** – klein, nützlich unabhängig von der Deployment-Form.

## 10. Phase 6 – Dokumentation

- [x] **6.1 README neu** ✅ – vorgezogen in 2.2, weil das Löschen von `default.nix` den
      dokumentierten `nix-shell`-Schritt gebrochen hatte. Enthält `nix develop`, Test-/Lint-Befehle,
      die drei Konfigurationswege, Deployment-Überblick und das Token-/Anonymitätsmodell.
- [x] **6.2 Handover statt `CLAUDE.md`** ✅ – [handover.md](handover.md) erfüllt denselben Zweck
      (Konventionen, Verifikationsschleife mit Sollwerten, Fallen) und ist auf Nachfrage des Users
      als Session-Einstieg gedacht. Eine `CLAUDE.md` wäre Duplikat; bei Bedarf später als
      Kurzfassung nachziehen.
- [x] **6.3 `notes/` aktuell halten** ✅ laufend – zuletzt vollständiger Konsistenzdurchgang
      (tote Links, `§`-Verweise, Bug-Status, überholte Aussagen).

---

## 11. Vorarbeit für Ziel 2 (Batch-Modus für Mails)

Spec kommt vom User. Bis dahin **nicht spekulativ implementieren**, aber Phase 3 so bauen, dass
folgende Punkte gegeben sind – sie sind für jede Variante von „Batch“ nötig:

1. ~~**Mail-Versand ist eine aufrufbare Service-Funktion**~~ ✅ mit 3.4 erledigt:
   `mail.poll_created_messages()` rendert, `mail.deliver()` verschickt. Ein Batch-Versender
   ersetzt `deliver()` und lässt das Rendern unberührt.
2. ~~**Kein SMTP im Request-Zyklus / nicht in der Transaktion**~~ ✅ mit 3.4 erledigt via
   `transaction.on_commit()` (B7). Der Callback rührt die Datenbank nicht an.
3. ~~**Mail-Inhalte als Django-Templates**~~ ✅ mit 3.4 erledigt – liegen unter
   `vote/templates/vote/mail/`, Autoescaping aus, Wortlaut per Test festgenagelt.
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
| ~~F10~~ | ~~Darf der tote Deployment-Code raus?~~ → **ja**, erledigt in `4e15012`. Nach Einsicht ins NixOS-Modul auch nachträglich als risikofrei bestätigt. | – |
| ~~F11~~ | ~~Wie wird deployt?~~ → **vollständig beantwortet**, Modul liegt vor. Analyse: **[notes/deployment.md](deployment.md)**. Wichtigstes Ergebnis: das Modul pinnt `rev = 3074dbb`, und die Django-Version kommt aus der nixpkgs des Colmena-Flakes – **zwei Änderungen im User-Repo nötig**, sonst erreicht das Upgrade Prod nicht. Löschcommit `4e15012` bestätigt risikofrei. | – |
| ~~F14~~ | ~~Setzt Prod `DEBUG = False`?~~ → **ja**, explizit im generierten `demockrazy_config`. Kein Leak, kein Hotfix. | – |
| **F15** | **Wie kommt Django in Prod ans `https`-Schema?** Node öffnet nur Port 80, kein `forceSSL`, kein `SECURE_PROXY_SSL_HEADER` im Modul – TLS wird vorgelagert terminiert. Setzt der Proxy `X-Forwarded-Proto`? Ohne diese Antwort keine TLS-/CSRF-Settings anfassen (Redirect-Schleife bzw. CSRF-403). | 2.7 |
| ~~F12~~ | ~~Prod-Schema-Stand?~~ → **geliefert.** Prod hat zwei Migrations (2016), DB liegt unter `/var/lib/demockrazy/db.sqlite3`. Ausgewertet in [notes/phase-2-migrations.md](phase-2-migrations.md). **Kleiner Rest inzwischen erledigt:** `PRAGMA table_info(vote_poll)` auf Prod bestätigt `type varchar(20) NOT NULL` an Position 8 und die Spaltenreihenfolge der zwei rekonstruierten Migrations. | – |
| F4 | Highcharts-Lizenz: existiert eine kommerzielle Lizenz, oder ersetzen? (B8) | 4.3 |
| F5 | Zugangsschutz für Poll-Erstellung – welche Variante? (B4/3.8) | 3.8, Ziel 2 |
| F8 | Anonymität vs. Zustellstatus pro Empfänger – wie weit darf Ziel 2 das aufweichen? (§11.4) | Ziel 2 |
| **F17** | **Überschreibt das NixOS-Modul einen der vier Mail-Text-Settings?** 3.4 hat `VOTE_MAIL_SUBJECT`, `VOTE_MAIL_TEXT`, `VOTE_ADMIN_MAIL_SUBJECT`, `VOTE_ADMIN_MAIL_TEXT` aus `settings.py` entfernt – der Text kommt jetzt aus Templates. Setzt `demockrazy_config` (oder die `djangoSettings`-Option) einen davon, wird der Wert nach dem Deploy **stillschweigend ignoriert** und Prod verschickt den Repo-Wortlaut. Prüfung im Repo des Users: `grep -rn 'VOTE_MAIL\|VOTE_ADMIN_MAIL\|VOTE_BASE_URL\|VOTE_MAIL_FROM'`. Meine Modul-Analyse in [deployment.md](deployment.md) listet keinen dieser vier, und die alte `local_settings.py` überschrieb nur `VOTE_BASE_URL`/`VOTE_MAIL_FROM`/`VOTE_SEND_MAILS` – die drei sind bewusst geblieben. Trifft die Annahme nicht zu, gehört der Text ins Template. | **vor dem Deploy** |
| F13 | Wie groß sind Abstimmungen real (Empfänger pro Poll, parallele Polls)? Entscheidet SQLite-Tuning vs. Postgres (B13) und die Batch-Größen für Ziel 2. | 5.4, Ziel 2 |
| ~~F16~~ | ~~Sind die drei Verschärfungen aus 3.1 gewollt?~~ → **ja**, vom User bestätigt (alle sechs Felder Pflicht, Djangos Adressvalidator, `title` auf 200 Zeichen). Seit 3.2 in der View wirksam. | – |

---

## 13. Reihenfolge / Abhängigkeiten

```
Phase 0  Baseline, Prod-Fakten                                        ✅
Phase 1  Tooling + Testsuite (das Sicherheitsnetz)                    ✅
Phase 2  Migrations, Django 5.2, Settings                             ✅ außer 2.7 (braucht F15)
Phase 5  5.1 k8s-Cleanup ✅ · 5.2 Deployment verstanden ✅ · 5.3 CI ✅ · 5.4/5.5 offen
Phase 6  README ✅ · Handover ✅

offen, in sinnvoller Reihenfolge:
  Phase 3  Code (3.1 Forms ✅ · 3.2 create()/manage() ✅ · 3.3 vote() ✅ · offen: 3.4–3.8)
             └─ 6 der 9 xfail-Tests sind weg, alle 3 roten Ruff-Befunde ebenfalls
             └─ 3.4 ist die Schnittstelle für Ziel 2
             └─ 3.8 braucht F5
             └─ liefert die Schnittstelle für ZIEL 2 (Batch-Mails, nach Spec)
  Phase 4  Frontend – unabhängig, parallelisierbar, 4.3 braucht F4
  5.4      SQLite-Härtung – braucht F13
  2.7      TLS-Hardening – braucht F15
```

**Nächster Schritt:** 3.7 (`re_path` → `path`, URLs identisch halten – Regel 4/5). Danach ist
von Phase 3 nur noch 3.8 offen, und das braucht F5.
**Vor dem Deploy:** F17 klären; die Migration `0003` schreibt `vote_poll` und `vote_token` neu
(Details in [phase-2-migrations.md](phase-2-migrations.md)), Backup liegt vor (borg 03:00/04:00).
**Die Vorarbeit für Ziel 2 (§11.1–3) ist mit 3.4 vollständig** – ein Batch-Versender ersetzt
`mail.deliver()`. Was noch fehlt, ist die Spec und die Entscheidung zu F8.
Details in [handover.md](handover.md) §9.
