# demockrazy – Modernisierungsplan

> Arbeitsdokument für Claude. Branch: `update/modernize-2026` (von `master`, Basis-Commit `3074dbb`).
> Angelegt: 2026-08-03. Notizen-Ordner: `notes/`.

---

## 0. Ziele

| # | Ziel | Status |
|---|------|--------|
| 1 | Projekt auf heutige Standards bringen (Django, Python, Nix, CI, Frontend, Deployment) | **Phase 0–6 vollständig ✅ außer 2.7. Das Bug-Register ist vollständig abgearbeitet** – B9 ist mit 3.9 gefallen. Offen ist nur noch 2.7, und das ist zum größten Teil **gegenstandslos** geworden, nachdem der Proxy vorliegt – es bleibt eine Frage (F15) und ein Vorschlag für den Proxy, nichts im Repo. |
| 2 | Batch-Modus für Mails bauen | **Gebaut** (§11.7): Warteschlange, getakteter Versender, Management-Command. 30er Batches / 2 s vom User vorgegeben. ⚠️ Der **systemd-Timer** fehlt noch und liegt außerhalb dieses Repos ([to-check.md](to-check.md) §C5). Offen: Bounce-Handling, Fortschrittsanzeige, **F20** |

| 3 | Umfassendes Review des ganzen Branches | **Geplant, §14.** Startet auf Zuruf des Users – **noch nicht gelaufen.** Umfang, Kriterien und Vorgehen stehen in [review.md](review.md), Befunde kommen ebenfalls dorthin |

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
| Frontend | Bootstrap 3.3.6 (2016), jQuery 2.2.4 (2016), Highcharts 4.2.5 (2016) – alle vendored | **alle drei ersetzt:** Bootstrap 5.3.8 (4.1), jQuery entfallen (4.2), Chart.js 4.5.1 statt Highcharts (4.3). 1,36 MB → 528 KB, Lizenzen durchgehend MIT |
| Datenbank (Prod) | **SQLite**, `/var/lib/demockrazy/db.sqlite3` | Lock-Risiko, siehe B13. *(Korrigiert: der Zusatz „+ `ATOMIC_REQUESTS=True`" war falsch – die Option war nie wirksam, B16.)* |
| k8s / Docker / sops | k8s-libsonnet 1.25, PG 14, GHCR-Images | **toter Code** – Deployment abgeschaltet, siehe Phase 5 |

### Bug-Register

| # | Kurz | Status |
|---|---|---|
| B1 | Migrations gitignored | ✅ **behoben** in 2.1 |
| B2 | `UnboundLocalError` in `vote()` | ✅ **behoben** in 3.3 |
| B3 | `create()` crasht bei GET / ungültigem Typ | ✅ **behoben** in 3.2 |
| B4 | Kein Auth/Rate-Limit auf `/vote/create` | ✅ **behoben** in 3.8 (Deckel 150) |
| B5 | Unsichere Settings-Defaults | ✅ **behoben** in 2.4 |
| B6 | Doppelte Adressen → doppelte Tokens | ✅ **behoben** in 3.1/3.2 |
| B7 | Mailversand innerhalb der Transaktion | ✅ **behoben** in 3.4 |
| B8 | Highcharts proprietär lizenziert | ✅ **behoben** in 4.3 (Chart.js, MIT) |
| B9 | Token im URL-Query-String | ✅ **behoben** in 3.9 (additiv: Umzug ins Cookie, Mail unverändert) |
| B10 | Templating in Inline-JS | ✅ **behoben** in 4.2 (`json_script`) |
| B11 | `manage()` crasht ohne `token`-Feld | ✅ **behoben** in 3.2 |
| B12 | `ValidationError` ungefangen | ✅ **behoben** in 3.1/3.2 |
| B13 | Prod läuft auf SQLite (Lock-Risiko) | ✅ **behoben** in 5.4 (WAL + IMMEDIATE + timeout) |
| B14 | TLS-Hardening unvollständig | **größtenteils gegenstandslos**: der Proxy setzt `forceSSL` + HSTS. Rest → 2.7, betrifft den Proxy, braucht F15 |
| B15 | `choice`-Wert ohne Zahl → 500 | ✅ **behoben** in 3.3 (neu gefunden) |
| B16 | `ATOMIC_REQUESTS` seit 2016 wirkungslos | ✅ **behoben** in 5.5 (neu gefunden); **F18** offen |
| B17 | Mehrzeilige `{# … #}` sind keine Kommentare | ✅ **behoben** in 4.2 (neu gefunden) |
| B18 | `.gitignore: static/` schloss die App-Assets aus | ✅ **behoben** in 4.1 (neu gefunden) |

Ursprünglich alle als `xfail(strict=True)` spezifiziert in
[vote/tests/test_known_bugs.py](../vote/tests/test_known_bugs.py). **Dort steht inzwischen kein
Marker mehr** – B2, B3, B4, B6, B9, B10, B11, B12 und die zwei Unique-Constraints sind
Regressionstests geworden. Von den 500-Pfaden ist keiner mehr offen. B15 kam erst in 3.3 dazu und war
sofort behoben, hatte also nie einen Marker.

**Mit 3.9 (B9) ist das Register vollständig abgearbeitet.** B14 ist der einzige Eintrag ohne Häkchen,
und der ist inhaltlich in 2.7 aufgegangen: was davon übrig ist, betrifft den Proxy.


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

**B13 – Produktion läuft auf SQLite.** *(Risikoeinschätzung mit B16 nach unten korrigiert)*
`local_settings.py` überschreibt `DATABASES` nicht ⇒ `django.db.backends.sqlite3`, und das Modul
startet **4 uwsgi-Prozesse** auf einer Datei. SQLite serialisiert Writer; wenn nach dem
Einladungsversand viele gleichzeitig abstimmen, sind `database is locked`-Fehler möglich.
**Falsch war der Zusatz „jeder Request nimmt eine Schreibtransaktion":** das setzte
`ATOMIC_REQUESTS = True` voraus, und die Option war nie wirksam (B16). Eine Transaktion nehmen nur
die zwei Stellen, die sie explizit aufmachen – die Stimmabgabe und die Umfrage-Erstellung. Das
Zeitfenster für einen Lock ist damit deutlich kleiner als angenommen, das Szenario aber nicht weg:
die Stimmabgabe *ist* der Moment, in dem viele gleichzeitig schreiben.
Auch für Ziel 2 relevant (Batch-Versand + Statusupdates).
Optionen für §12: SQLite mit WAL + `timeout` tunen (klein, reversibel) vs. Postgres (größer).
Vorher messen, nicht raten – und klären, wie oft/wie groß Abstimmungen real sind.

**B14 – TLS-Hardening-Settings fehlen in Prod.** *(korrigiert 2026-08-03)*
`SESSION_COOKIE_SECURE` und `CSRF_COOKIE_SECURE` **sind** gesetzt – das Modul macht das über
`secureCookies` (Default `true`). Der Befund war insoweit zu pauschal.
Als fehlend notiert waren `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, `CSRF_TRUSTED_ORIGINS` und
`SECURE_PROXY_SSL_HEADER`. **Mit der Proxy-Config (2026-08-04) ist das überholt:** dort stehen
`forceSSL` und HSTS bereits, die ersten zwei wären in Django also doppelt und gehören **nirgendwohin**
– auch nicht ins Modul. Offen ist nur noch, ob `X-Forwarded-Proto` ankommt (F15); davon hängt ab, ob
`SECURE_PROXY_SSL_HEADER` oder `CSRF_TRUSTED_ORIGINS` gebraucht wird.
→ 2.7, Details in [notes/deployment.md](deployment.md), Handlungsliste in [to-check.md](to-check.md).

**B11 – `manage()` crasht bei POST ohne `token`-Feld.**
[vote/views.py](../vote/views.py) – `request.POST['token']` ohne Guard → `MultiValueDictKeyError` → 500.
Gleiche Klasse wie B3, eigene Stelle.

**B12 – `ValidationError` aus `parse_mails()` wird nicht gefangen.**
Eine ungültige Mailadresse im Empfängerfeld führt zu einem 500 statt zu einer Formularmeldung –
und legt unter `DEBUG=True` die *gültigen* Adressen der Liste offen (siehe B5).

**B6 – Doppelte Mailadressen bekommen doppelte Tokens.**
`parse_mails()` dedupliziert nicht → dieselbe Person kann zweimal wählen.

**B7 – Mails werden synchron im Request versendet.** *(Mechanismus mit B16 korrigiert)*
Ursprünglich als „`ATOMIC_REQUESTS = True` + `send_mail()` in der Transaktion" beschrieben. Die
Option war nie wirksam (B16), eine Request-Transaktion gab es also nicht. Der Befund bleibt, nur
anders begründet: `create()` verschickte die Mails **in der Save-Schleife**, während die Tokens
entstanden – ohne jede Transaktion. Ein Fehler auf halbem Weg ließ Mails draußen *und* halbe Daten
zurück, und ein hängender SMTP-Server blockierte den Request. ✅ Behoben in 3.4/3.5: `create_poll()`
ist atomar, der Versand hing an `on_commit`. *(Nachtrag §11.7: das `on_commit` ist entfallen -- eingereiht wird in derselben Transaktion, verschickt in einem anderen Prozess.)*
→ Kernmotivation für Ziel 2.

**B18 – `.gitignore` schloss die Quell-Assets der App aus.** *(neu gefunden in 4.1)*
Die Regel war `static/`, eingeführt in `72871d9` (2016-06-09). **Ohne führenden Slash trifft das
jedes Verzeichnis namens `static` auf jeder Ebene** – gemeint war `STATIC_ROOT` (die
`collectstatic`-Ausgabe unter `BASE_DIR`), getroffen wurde zusätzlich `vote/static/` mit den
Quell-Assets, die ins Repo *gehören*.
**Der Beleg ist, was dort getrackt war:** nur `css/main.css` und `highcharts-custom.js`, beide älter
als die Regel, plus das Bootstrap-3-Verzeichnis. Jedes seither hinzugefügte Asset fiel still heraus –
`git add` verweigerte ohne `-f`. Aufgefallen, weil ich beim Vendoren von Bootstrap 5 hineingelaufen
bin: die neuen Dateien wären nicht mitgekommen, und in Produktion hätte die Seite kein CSS gehabt.
✅ Auf `/static/` verankert, also auf das, was `STATIC_ROOT` tatsächlich ist.

**B8 – Highcharts 4.2.5 ist proprietär lizenziert.**
Kein Free-/Open-Source-Lizenzmodell für kommerzielle Nutzung. Vendored in
`vote/static/highcharts-custom.js` in einem MIT-Repo (die Datei ist mit 4.3 entfernt).
→ Durch Chart.js (MIT) oder ECharts (Apache-2.0) ersetzen. **Lizenzfrage an User weitergeben.**

**B9 – Token im URL-Query-String.** ✅ **behoben in 3.9**
`?token=…` landete im nginx-Access-Log des Hosts, im Referer und in der Browser-History, und der
Token ist das einzige Auth-Merkmal. Eine Änderung war nur **additiv** möglich (Regel 4: es sind Mails
mit solchen Links unterwegs). Umgesetzt ist deshalb nicht ein neuer Einlöseweg, sondern ein
**Umzug**: der erste Aufruf legt den Token in ein pfadgebundenes Cookie und leitet auf dieselbe
Adresse **ohne Query-String** um. Der Link in der Mail bleibt zeichengleich, alte Links funktionieren
weiter, der Token lebt in der URL nur noch für einen Request. Details und Messungen bei 3.9.

**B15 – `choice`-Wert ohne Zahl ergibt einen 500.** *(neu gefunden in 3.3)*
`poll.choice_set.get(pk=request.POST["choice"])` wirft bei einem nicht-numerischen Wert
(`"abc"`, `""`) einen `ValueError`, nicht `Choice.DoesNotExist` – und den fing niemand.
Auslösbar von jedem, der einen gültigen Token hat, mit einem handgebauten POST. Kein Datenleck
(Prod läuft mit `DEBUG=False`), aber ein 500 im Log statt einer Fehlermeldung.
Gemessen, nicht vermutet: `"abc"`, `""` und `"1; DROP TABLE"` → 500, `"9"*20` → 200 mit
Fehlermeldung (das ist eine Zahl, nur keine existierende ID).
✅ **Behoben in 3.3** zusammen mit B2, weil es dieselbe Klasse ist: ungeprüfter POST-Zugriff.

**B10 – Templating in Inline-JS.**
[vote/templates/vote/results.html](../vote/templates/vote/results.html) interpolierte `choice_text`
direkt in ein JS-String-Literal. Django-Autoescaping verhinderte einen Ausbruch, mangelte aber die
Anzeige. ✅ **Behoben in 4.2** über `json_script` – Details dort.

**B17 – Mehrzeilige `{# … #}` sind in Django keine Kommentare.** *(neu gefunden in 4.2)*
Djangos `tag_re` ist **ohne `re.DOTALL`** kompiliert: ein `{#` findet sein `#}` nur in derselben
Zeile. Alles darüber hinaus bleibt Text – **inklusive der `{{ … }}` darin, die dann ausgewertet
werden.** Drei Vorkommen im Bestand (`create.html`, `index.html`, und eines, das ich in 4.2 selbst
erzeugt habe).
**Warum es nie auffiel:** die zwei alten stehen *außerhalb* jedes `{% block %}` eines
Kind-Templates, und das verwirft Django. Wer sie nach innen verschiebt, leakt sie.
**Wie es zuschlug:** in meiner Prosa stand das Wort „script" in spitzen Klammern – der HTML-Parser
öffnete daran ein `script`-Element und verschluckte das Datenelement dahinter. Die Seite lieferte
einen sauberen **200 ohne Diagramm**; `curl` sah korrekt aus, erst der DOM im Browser zeigte es.
Genau dafür lohnt der Browser-Gegencheck bei JS-/Markup-Änderungen.
✅ Alle drei auf `{% comment %}` umgestellt, plus ein Wächter-Test in
[vote/tests/test_templates.py](../vote/tests/test_templates.py), der den Template-Baum abläuft.

### Kleinere Punkte

Erledigt: `/healthz` (5.5) · Cache-Busting (4.4) · Template-Defekte (4.5) · `USE_L10N` (2.4) ·
`DEFAULT_AUTO_FIELD` (2.4) · `manage.py`-Boilerplate (2.5) ·
README/`pip3 install django==2.2.27` (2.2) · `LOGGING` (setzt das Prod-Modul) ·
Static-Handling aus dem Source-Tree (mit den Docker-Images in `4e15012` weg) ·
`len(Token.objects.filter(…))` → Zählen in der Datenbank (3.6) ·
`mk_token()`/`mk_identifier()`-Rekursion (3.6 – die Kollisionsprüfungen sind ganz weggefallen, es
gibt nichts mehr zu rekursieren) · `re_path` überall (3.7).

Gegenstandslos: **kein `HttpResponseNotAllowed`-Handling**. War für 3.2 vorgesehen und dort bewusst
verworfen – ein GET auf `/vote/create` rendert das Formular, weil ein 405 für einen Menschen aus der
Browser-History eine Sackgasse ist. Begründung bei 3.2.

Damit ist von den kleineren Punkten **keiner mehr offen.** *(Hier stand bis zuletzt
„Bootstrap-3-Markup durchgehend → 4.1" – das ist mit 4.1 erledigt, im Markup steht keine
Bootstrap-3-Klasse mehr.)*

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
9. **Im Workspace bleiben.** Arbeiten und suchen nur in `~/Desktop/wahlcomputer-update/demockrazy`.
   Was von außen gebraucht wird – das NixOS-Modul, das Colmena-Repo, Ausgaben von der Prod-Node –
   **beim User erfragen**, nicht im Dateisystem suchen. Er liefert es; so sind F12, die
   Duplikat-Prüfung vor 3.6 und der `PRAGMA`-Nachtrag entstanden. Ausführlich in
   [handover.md](handover.md) §10, Regel 10.
10. **Code-Kommentare und Docstrings sehr kurz.** Ein bis zwei Zeilen, die auf die Begründung
   *zeigen* (`Plan §11.7`, `B9`, `F8`), statt sie zu enthalten. Vom User am 2026-08-04 gewünscht.
   **Dieses Dokument bleibt ausführlich** – hier gehört die Argumentation hin, und dann steht sie an
   genau einer Stelle. Hinten angehängt, weil die Nummern 1–9 überall referenziert sind.

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
      Models, alle sieben Views, Anonymitätsgarantien, plus ein URL-Form-Test als Absicherung von
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
      `makemigrations --check` sauber. **Deploy: `0001`/`0002` sind in Prod ein garantierter No-Op,
      kein `--fake-initial`.** *(Nachtrag 3.6: für `migrate` insgesamt gilt das nicht mehr – `0003`
      wird angewendet und schreibt zwei Tabellen neu, siehe 3.6 und
      [phase-2-migrations.md](phase-2-migrations.md).)* Frischer Clone verifiziert: 56 grün, 9 xfailed (Stand 2.1).
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
- [ ] **2.7 TLS-Hardening – neu gefasst, nachdem der Proxy vorliegt (F15 teilweise beantwortet).**
      **Das Ziel "`check --deploy` grün" war falsch gesetzt.** Der User hat die Config des
      vorgelagerten nginx geliefert (Analyse: [deployment.md](deployment.md)), und daraus folgt:
      - `SECURE_SSL_REDIRECT` **nicht setzen** – `forceSSL = true` macht die Umleitung schon oben.
      - `SECURE_HSTS_SECONDS` **nicht setzen** – HSTS steht dort mit einem Jahr; in Django wäre es
        ein **zweiter** `Strict-Transport-Security`-Header, also undefiniertes Verhalten statt Schutz.
      - ⇒ `check --deploy` wird für diese zwei **dauerhaft meckern, und das ist richtig so.** Der
        Check kann den Proxy nicht sehen. Grün wäre hier nur durch doppelte Header zu erkaufen.
      **Neuer Nebenbefund:** `X-Frame-Options` ist heute **widersprüchlich** – Proxy sagt
      `sameorigin`, Djangos Middleware `DENY`, beide Header gehen raus. Bei widersprüchlichen Werten
      ist Browserverhalten nicht festgelegt, im schlechtesten Fall wird der Header ignoriert. Eine
      Seite sollte ihn besitzen; da die App nicht eingebettet werden soll, ist Djangos `DENY` das
      strengere und das Snippet für diesen vhost überflüssig.
      **Was wirklich offen ist:** kommt `X-Forwarded-Proto` bei Django an? Ohne den Header hält Django
      den Request für `http`, und die CSRF-Origin-Prüfung müsste **jede Stimmabgabe mit 403**
      abweisen. Sie tut es nicht, also liefert etwas das Schema – Header oder `CSRF_TRUSTED_ORIGINS`.
      Gebraucht wird `services.nginx.recommendedProxySettings` auf dem Proxy-Host und der
      vollständige `proxyPass`.
      **Wirksamster verbleibender Schritt, und er gehört nicht ins Repo:** den vorhandenen
      `nginxCSPSnippet` auf diesen vhost einbinden. Das ging vorher nicht sinnvoll, geht aber jetzt –
      **seit 4.1/4.3 ist alles vendored**, es gibt keinen Fremd-Host mehr, und das inline-Script der
      Ergebnisseite ist durch das `'unsafe-inline'` des Snippets gedeckt.

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
      `poll_created_messages()` baut die Liste, `deliver()` verschickte sie – ein Batch-Versender
      sollte genau das zweite ersetzen. *(Nachtrag §11.7: genau so gekommen. `deliver()` ist weg,
      an seiner Stelle stehen `enqueue()` und `send_pending()`.)*
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
      Management-Command (Ziel 2) sie genauso aufrufen kann. `transaction.atomic` drauf – **hier
      stand „im Request redundant (`ATOMIC_REQUESTS`, dort nur ein Savepoint)", und das war falsch:**
      die Option war nie wirksam (B16), der Dekorator ist das Einzige, was die Funktion atomar macht.
      Gut, dass er da ist.
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
      **Die letzten zwei `xfail`-Marker sind weg**, offen war zu diesem Zeitpunkt nur noch B4
      *(inzwischen mit 3.8 behoben, es gibt keinen `xfail` mehr)*.
      Ein `per-file-ignore` dazugekommen: `RUF012` für `vote/models.py`, weil eine Liste Djangos
      dokumentierte Schnittstelle für `Meta.constraints` ist.
- [x] **3.7 `re_path` → `path`** ✅ – sieben der acht Routen brauchten nie einen Ausdruck; die
      Anker (`^…$`) trugen dort Bedeutung, die `path()` von sich aus mitbringt. Die sieben
      öffentlichen Pfade sind zeichengleich geblieben (Regel 4).
      **`<slug:…>` ist wie vermutet kein Ersatz** und wurde nicht genommen: es lässt zusätzlich `-`
      und `_` zu und würde Kennungen annehmen, die es nicht gibt – `mk_identifier()` zieht nur aus
      `ascii_letters + digits`. Stattdessen ein eigener Converter mit genau der alten Zeichenklasse,
      per `register_converter` in [vote/urls.py](../vote/urls.py) neben der Route, die ihn braucht.
      **Gemessen statt angenommen:** 23 Pfade (die sieben Routen, Trailing-Slash-Varianten, `/admin/`
      und Kennungen mit `-`, `_`, `.`, Leerzeichen und einem Nicht-ASCII-Buchstaben) lösen vorher und
      nachher identisch auf, `reverse()` liefert dieselben Strings. Zwei der Fälle stehen jetzt in
      `test_views.py::TestUrls` als Absicherung (**+4 Tests**).
      *Nebenbefund, unverändert übernommen:* `/vote/create/` (mit Slash) fällt auf
      `vote:polls:poll` mit `poll_identifier="create"` und endet im 404 von `get_object_or_404` –
      genau wie vorher, nur über einen anderen Weg. Kein Handlungsbedarf (Regel 3).
- [x] **3.8 Zugangsschutz für `create` (B4)** ✅ – **F5 entschieden: Deckel auf die Empfängerzahl,
      kein IP-Rate-Limit.** `VOTE_MAX_RECIPIENTS = 150` (vom User gewählt), konfigurierbar über
      `DEMOCKRAZY_MAX_RECIPIENTS`, mit sicherem Default statt keinem – Prinzip aus 2.4.
      **Nach der Deduplizierung gezählt:** begrenzt werden soll die Zahl der *Mails*, und 200 Zeilen
      mit 150 Dubletten sind 50 Mails.
      ⚠️ **Es ist Missbrauchsschutz, keine Lösung für das Rate-Limit des Mailservers** (§11): der
      antwortet ab ~50 Nachrichten pro Zeitfenster mit `450`. Eine Umfrage mit 150 Empfängern ist
      also erlaubt und erst mit dem getakteten Versand zustellbar. Die zwei Grenzen sind unabhängig.
      **Der B4-Test hat mit dem Marker auch seine Erwartung verloren:** solange die Maßnahme offen
      war, verlangte er einen ablehnenden Statuscode (400/401/403/429). Ein Deckel im Formular ergibt
      einen **200 mit Fehlermeldung** – wie jede andere ungültige Eingabe, und aus demselben Grund
      (der Ersteller soll kürzen können, nicht in einer Sackgasse landen, 3.2). Geprüfte Zusage ist
      jetzt die *Wirkung*: keine Umfrage, keine Mail, auch nicht an den Ersteller.
      **Das war der letzte `xfail` der Suite** – seither gibt es keinen mehr, und der Sollwert hat
      kein `xfailed` mehr. Die aktuelle Zahl steht in [handover.md](handover.md) §4, nicht hier.
- [x] **3.9 Token raus aus dem Query-String (B9)** ✅ – **nachträglich zu Phase 3 dazugekommen**, weil
      es eine Code-Änderung in [vote/views.py](../vote/views.py) ist und keine Deployment-Frage.
      **Kein neuer Einlöseweg, sondern ein Umzug:** `poll()` nimmt einen Token aus `?token=`, legt ihn
      in ein Cookie und leitet auf dieselbe Adresse **ohne Query-String** um. Danach kommt der Token
      aus dem Cookie ins Formularfeld. **Damit bleibt alles additiv** (Regel 4/5): der Mailtext ist
      unverändert, `poll_url_with_token` sieht aus wie immer, alte Links funktionieren, und die
      Stimmabgabe liest den Token weiter aus dem POST-Body – das Cookie ist eine Bequemlichkeit für
      die Anzeige und **kein Auth-Kanal** (eigener Test).
      **Warum es sich lohnt, gemessen statt zitiert:** der Token stand nicht nur einmal im Log. Im
      Browser nachgesehen – Django schickt `Referrer-Policy: same-origin`, und unter dieser Policy
      sendet der Browser für gleichherkünftige Anfragen die **vollständige** URL: nach einem Klick von
      `/vote/<id>/?beispiel=…` auf `/vote/` stand in `document.referrer` der komplette Query-String.
      Der Token reiste also in jeder Unteranfrage der Seite mit, Stylesheet inklusive. Nach dem Umzug
      sind es **genau zwei Logzeilen mit `?token=` für zwei angeklickte Einladungen**, danach keine.
      ⚠️ **Was offen bleibt und offen bleiben muss:** die Logzeile dieses *einen* Aufrufs. Sie hängt
      an einem klickbaren Link; nginx protokolliert die Anfragezeile, bevor Django sie sieht. Lösbar
      nur am Proxy über ein `log_format` ohne `$args` → [to-check.md](to-check.md) §B3.
      **Die Kosten sind null, und das ist gemessen, nicht gehofft:** ein POST ohne Cookie ist heute
      schon ein **403**, weil Djangos CSRF-Prüfung ein Cookie verlangt. Wer keine annimmt, konnte
      auch vorher nicht abstimmen – ein zweites Cookie nimmt also keinem Wähler etwas.
      **Vier Cookie-Eigenschaften, jede mit einem Grund** (ausführlich im Code):
      `path` auf `/vote/<id>/` – ohne das würde eine zweite Einladung die erste überschreiben, was
      mit `?token=` in der URL nicht passierte; die Bindung ist also Verhaltenserhaltung. `httponly`,
      weil kein Skript den Token braucht. `samesite="Lax"` und **nicht** `"Strict"`: der Klick aus
      einem Webmailer ist eine seitenübergreifende Navigation, bei `Strict` käme das Cookie dort nicht
      mit und die Weiterleitung liefe ins Leere. `secure` aus `SESSION_COOKIE_SECURE`, weil das
      Prod-Modul genau diesen Schalter schon setzt (`secureCookies`) – ein eigener würde still davon
      abweichen, und `not DEBUG` zur Importzeit wäre falsch, weil `demockrazy_config` `DEBUG` erst
      *nach* dem Sternchen-Import setzt.
      **Kein neuer Zustand auf dem Server**, insbesondere **keine Session:** die hätte für jeden
      Besucher eine Zeile in `django_session` geschrieben, also einen Schreibzugriff auf dieselbe
      SQLite-Datei, die vier uwsgi-Prozesse teilen (B13) – gegen den 5.4 gerade gearbeitet hat.
      **Zwei Nebenentscheidungen, die man wissen will:** die `is_active`-Weiche ist an den Anfang der
      View gewandert, damit eine geschlossene Umfrage mit Token nicht erst umzieht und dann zweimal
      weiterleitet; und das Cookie wird nach der Abgabe **nicht** gelöscht, weil dann dieselbe Meldung
      erscheint wie bisher beim erneuten Aufruf des Mail-Links („This token is invalid. Maybe you
      voted already?") statt eines leeren Feldes.
      **Lebensdauer 30 Tage.** Ein Sitzungscookie wäre strenger, würde aber etwas wegnehmen, was heute
      funktioniert: in der History steht nach dem Umzug nur noch die Adresse ohne Token, ein Aufruf
      von dort käme ohne Token an. Die Einladung in der Mailbox verfällt gar nicht; 30 Tage sind
      kürzer als das. **Falls kürzer gewünscht ist, ist es eine Zeile** in `vote/views.py`.
      `Vary: Cookie` ist explizit gesetzt, obwohl die CSRF-Middleware ihn heute schon mitliefert
      (gemessen) – der Header soll aus dem Grund dastehen, aus dem er gebraucht wird.
      **Im Browser gegengeprüft, weil der Testclient das Wesentliche nicht sieht:** die Adressleiste
      ist nach dem Klick token-frei, `document.cookie` zeigt nur `csrftoken` (das Token-Cookie ist
      `httponly`), zwei parallele Einladungen behalten **jede ihren eigenen** Token – die Kantinen-Seite
      ohne Query-String zeigte den Kantinen-Token, während das Sommerfest-Cookie ebenfalls lag –, und
      einmal echt abgestimmt: POST → 302 → `/success` 200, danach die „voted already"-Meldung.
      Der Testclient kann das nicht: sein Cookie-Speicher ist nur nach Namen sortiert und ignoriert
      `path`, dort würde die Isolation *scheinbar* auch ohne sie gelingen.

## 8. Phase 4 – Frontend

- [x] **4.1 Bootstrap 3.3.6 → 5.3.8** ✅ – vendored, kein CDN (die Seite soll ohne Fremdverbindung
      laufen, ein CDN wäre der einzige externe Host im Dokument). **Version gegen die GitHub-API
      geprüft, nicht erinnert:** v5.3.8 (2025-08-26) ist das aktuellste Release. Nur
      `bootstrap.min.css` + `bootstrap.bundle.min.js` (das Bundle enthält Popper), keine Maps.
      Herkunft, Checksummen und die **eine** Änderung stehen in
      [vote/static/bootstrap-5.3.8-dist/PROVENANCE.md](../vote/static/bootstrap-5.3.8-dist/PROVENANCE.md).
      **Diese Änderung ist keine Kosmetik:** beide Bundles enden mit einem `sourceMappingURL`-Verweis
      auf die nicht mitgelieferten `.map`-Dateien, und `ManifestStaticFilesStorage` (4.4) löst solche
      Verweise auf und **bricht ab**, wenn das Ziel fehlt. `collectstatic` läuft in Prod im
      `preStart` – ein Abbruch dort heißt, der Dienst startet nicht. **Der Test aus 4.4 hat es
      gefangen**, genau der Fall, für den er geschrieben wurde. Letzte Zeile jeder Datei entfernt.
      Klassen-Migration: `form-group` → `mb-3`, `<select>` → `form-select`, Labels → `form-label`,
      `navbar-inverse`/`navbar-fixed-top`/`navbar-toggle`/`icon-bar` → 5.x-Navbar mit `data-bs-*`,
      `sr-only` → `visually-hidden`. **`body { padding-top }` folgt der gemessenen Navbar-Höhe:**
      56px in 5.3.8 gegen 50px in 3 – der alte Wert verdeckte die Überschrift um 6px.
      **Drei vorbestehende Markup-Defekte mitbehoben:** `token_state.html` war ein
      `ul.nav.nav-pills` mit `role="tablist"`/`role="presentation"` für etwas, das weder Navigation
      noch Tabs ist (ein Screenreader kündigte Reiter an, die niemand anklicken kann), plus ein
      führendes leeres `<label>`; die Radios in `poll.html` standen ohne Gruppierung, getrennt von
      `<br/>`; und die ja/nein-Radios der Multiple-Choice-Matrix hatten **gar keinen zugänglichen
      Namen** – nur ein `<label>` ohne `for` in der Textspalte, das auf nichts zeigte.
      **`name`/`id` sind zeichengleich geblieben** (`choice`, `choice<pk>` mit `yes`/`no`): daran
      hängt `vote()`, und es sind Mails mit Links auf offene Umfragen unterwegs.
      **Im Browser verifiziert**, weil pytest davon nichts sieht: keine Bootstrap-3-Reste und kein
      jQuery auf allen sechs Seiten, keine leeren Labels, kein `for` ins Leere, Navbar-Toggler
      öffnet und schließt ohne jQuery, Chart rendert, kein horizontaler Überlauf bei 375px – und
      **einmal echt abgestimmt**: POST auf `/vote/<id>/vote`, Redirect auf `/success`, Stimme
      gezählt, Token gelöscht, Umfrage automatisch geschlossen.
- [x] **4.2 jQuery entfernen** ✅ – in zwei Schritten. Zuerst der Chart-Init in `results.html`:
      **im vendorten File geprüft statt angenommen**, Highcharts 4.2.5 ist standalone und registriert
      `$.fn.highcharts` nur, *wenn* jQuery da ist – `new Highcharts.Chart({chart: {renderTo: …}})`
      ist die 4.x-API (das kleingeschriebene `Highcharts.chart` gibt es erst ab 5.x). Kein
      Ready-Handler nötig, der Block rendert am Ende von `<body>`.
      Danach mit 4.1 der letzte Nutzer: Bootstrap 3s JS brauchte jQuery für die einklappende Navbar.
      `jquery-2.2.4.min.js` ist weg.
- [x] **B10 mit 4.2 behoben** ✅ – Diagrammdaten kommen per `json_script` aus der View statt als in
      ein JS-Stringliteral interpolierte Werte. **Vorher gemessen:** betroffen waren `&`, `'`, `"`
      und `<` – im Diagramm stand sichtbar `Bier &amp; Brezn`, wo die Tabelle `Bier & Brezn` zeigte.
      Regressionstest in [test_known_bugs.py](../vote/tests/test_known_bugs.py).
      **Eine bewusste kosmetische Änderung:** ein Choice-Text mit Markup (`<b>x</b>`) rendert im
      Diagramm jetzt *fett*, statt die Entities zu zeigen – Highcharts parst in Labels eine kleine
      Tag-Whitelist. **Geprüft, ob daran mehr hängt: nein** – `javascript:`-Hrefs und `on*`-Handler
      werden gestrichen, heraus kommen nur `<tspan>`s. Wörtlich anzeigen ginge erst mit dem
      Bibliothekswechsel – *und mit 4.3 ist genau das eingetreten: Chart.js zeichnet auf ein Canvas,
      das kein Markup kennt, der Text erscheint jetzt wörtlich.*
      Nebeneffekt: `choice_set` wurde für Tabelle und Diagramm zweimal abgefragt, jetzt einmal.
- [x] **4.3 Highcharts ersetzt (B8)** ✅ – **Chart.js 4.5.1, MIT** (F4). Damit ist das Frontend
      durchgehend MIT/Apache, der Lizenztext liegt als `LICENSE.md` daneben.
      **Aus dem npm-Tarball statt von einem GitHub-Asset**, weil npm pro Version einen `shasum`
      veröffentlicht – Herkunft, die man prüfen kann statt ihr zu glauben; geprüft, `sha1` stimmt.
      Details in [chartjs-4.5.1/PROVENANCE.md](../vote/static/chartjs-4.5.1/PROVENANCE.md), samt
      derselben `sourceMappingURL`-Änderung wie bei Bootstrap und aus demselben zwingenden Grund.
      **Chart.js lädt nur `results.html`, nicht `base.html`** – Highcharts hing dort und ging damit
      auf alle sechs Seiten mit, für ein Diagramm, das auf einer erscheint.
      Der Prozentwert steht im Label statt in einem Datalabel-Plugin: ohne Hover und im Ausdruck
      lesbar, und es bleibt bei *einer* Abhängigkeit. Palette fest statt Chart.js' Automatik, weil
      die Zahl der Optionen vorab unbekannt ist. Das Canvas trägt ein knappes `aria-label` und
      keinen Nachbau seines Inhalts – die Tabelle darüber hat alle Zahlen und *ist* die zugängliche
      Fassung.
      **Ein Gewinn nebenbei:** ein Choice-Text mit Markup wird jetzt wörtlich angezeigt. Highcharts
      parste in Labels eine Tag-Whitelist, `<b>x</b>` wurde dort fett; ein Canvas kennt das nicht.
      ~~Daten über `json_script` statt Inline-Interpolation (B10)~~ – **mit 4.2 vorab erledigt**.
      **Zur Verifikation ein Umweg, der notiert gehört:** `requestAnimationFrame` feuert in der
      automatisierten Browser-Pane nicht, Chart.js zeichnete deshalb nie und das Canvas las sich als
      leer – ein Artefakt der Umgebung, kein Befund über die Konfiguration. `chart.draw()` umgeht den
      Animator: 34,9 % des Canvas gefüllt, die drei Palettenfarben decken 15936 / 8193 / 4377 Pixel,
      also **4:2:1 bei Stimmen 4:2:1**. Enthaltungen mit 0 zeichnen nichts.
- [x] **4.4 Cache-Busting für Static Files** ✅ – `STORAGES["staticfiles"]` auf
      `ManifestStaticFilesStorage`. **Kein Whitenoise** – nginx serviced `/static` schon direkt aus
      `/var/lib/demockrazy/static` (siehe §1), gebraucht wird der Dateiname, nicht ein zweiter Server.
      Zwei Dinge machen es gefahrlos: `collectstatic --noinput` läuft im `preStart` bei **jedem**
      Service-Start, das Manifest ist also nie veraltet; und bei `DEBUG=True` hasht Django gar nicht
      (`HashedFilesMixin._url`), `runserver` braucht kein collectstatic.
      **Vorab gemessen, nicht gehofft:** `collectstatic` mit Manifest-Storage läuft gegen den
      *aktuellen* Bestand durch – 146 Dateien post-processed, alle `url()`-Verweise von Bootstrap 3
      (Glyphicon-Fonts) lösen auf. Damit war 4.4 **nicht** von 4.1 abhängig.
      **`test_settings.py` stellt bewusst auf `StaticFilesStorage` zurück** – auch das gemessen: ohne
      den Override fallen **56 Tests** mit `Missing staticfiles manifest entry` um, weil die Suite mit
      `DEBUG=False` läuft und das Manifest erst `collectstatic` schreibt.
      Der neue Test in [demockrazy/tests/test_staticfiles.py](../demockrazy/tests/test_staticfiles.py)
      **fährt `collectstatic` wirklich**: der Fehlerfall ist nicht ein falscher Dateiname, sondern ein
      **Abbruch**, wenn eine CSS-Datei per `url()` ins Leere zeigt – und das Kommando läuft in Prod im
      `preStart`, ein Abbruch dort heißt, der Dienst startet nicht. Steht damit vor 4.1 bereit.
- [x] **4.5 Template-Kleinkram** ✅ – drei Punkte, alle versionsunabhängig und deshalb vor 4.1 gemacht:
      `<th>…</td>` in [results.html](../vote/templates/vote/results.html) korrekt geschlossen und die
      Kopfzeile in ein `<thead>` mit `scope="col"` gesetzt; das **doppelt eingebundene
      `bootstrap.css`** in [base.html](../vote/templates/base.html) entfernt (jeder Besucher lud
      dieselben ~120 KB zweimal – im Browser gegengeprüft, jetzt ein Request pro Asset);
      `aria-describedby` + `aria-invalid` auf die Fehlerlisten in
      [index.html](../vote/templates/vote/index.html), **nur wenn ein Fehler vorliegt** (ein
      `aria-invalid="false"` auf jedem Feld ist Lärm, ein `aria-describedby` auf einen leeren
      Container eine Zusage, die niemand einlöst). Test prüft beide Richtungen.
      ~~`lang="de"` wo die Texte deutsch sind~~ – **gegenstandslos, die Annahme war falsch:** die
      Web-UI ist durchgehend **englisch** („create a new poll", „Total Voters", „Redeemed"), nur die
      *Mails* sind deutsch. `lang="en"` in `base.html` ist damit korrekt und bleibt.

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
- [x] **5.4 SQLite-Betrieb absichert (B13)** ✅ – **kein Postgres**: F13 sagt 60–100 Empfänger, das
      trägt SQLite. Drei Optionen in `DATABASES['default']['OPTIONS']`, und die wichtigste ist nicht
      die naheliegende:
      **`transaction_mode="IMMEDIATE"`.** Djangos Default ist `DEFERRED`, da nimmt SQLite die
      Schreibsperre erst beim ersten Schreibzugriff. Eine Transaktion, die mit einem SELECT anfängt
      und danach schreibt – **genau die Form von `vote()`** – muss ihre Leseperre hochstufen, und das
      kann SQLite nicht warten lassen: sofortiges `SQLITE_BUSY`, **ohne `timeout` zu beachten**.
      `IMMEDIATE` nimmt die Sperre beim BEGIN, damit greift der `timeout`.
      **Gemessen statt begründet**, 8 Threads × 25 Lese-dann-Schreib-Transaktionen auf einer Zeile:
      mit Djangos Defaults **36 von 200 erfolgreich, 164 × `database is locked`**; mit den Optionen
      **200 von 200**, Zähler exakt 200, für 0,13 s mehr Laufzeit. Die Konkurrenz ist absichtlich
      härter als die Realität (echte Wähler kommen verteilt), aber der Mechanismus greift bei jeder
      echten Gleichzeitigkeit – also genau nach dem Einladungsversand.
      **Hier zahlt sich F18 aus:** `IMMEDIATE` ist nur deshalb billig, weil `ATOMIC_REQUESTS` aus
      bleibt. `atomic()` gibt es an den zwei Stellen, die schreiben. Mit ATOMIC_REQUESTS würde
      `IMMEDIATE` *jeden* Request serialisieren, auch die Ergebnisseite.
      **WAL** dazu, damit Leser und Schreiber sich nicht blockieren. **Bewusst kein
      `synchronous=NORMAL`**, was sonst gern mit WAL empfohlen wird: das tauscht Dauerhaftigkeit
      gegen Geschwindigkeit, und hier sind Commits *Stimmen*.
      **Backup war schon geklärt:** borg onsite 03:00 + offsite 04:00 auf `/var/lib/demockrazy`;
      WAL legt `-wal`/`-shm` daneben, die werden mitgesichert.
      ⚠️ **Die Falle ist dieselbe wie bei B16:** `demockrazy_config` setzt `DATABASES` komplett neu
      und verliert die `OPTIONS` – still, genau wie zehn Jahre lang bei `ATOMIC_REQUESTS`. Deshalb
      liegt ein **System-Check** dabei ([demockrazy/checks.py](../demockrazy/checks.py)), der das
      Fehlen meldet. Gegen die echten Prod-Settings prüfbar mit
      `DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check`.
      Ohne `Tags.database`, weil `check` so getaggte Checks ohne `--database` auslässt – dann wäre er
      genau in der Situation still, für die er existiert.
      Testbar ohne Modul-Änderung über die `djangoSettings`-Option des Moduls.
- [x] **5.5 `/healthz`-Endpoint** ✅ – in [demockrazy/views.py](../demockrazy/views.py), geroutet aus
      [demockrazy/urls.py](../demockrazy/urls.py). Projektebene, nicht `vote`: es ist ein
      Betriebs-Endpunkt und liegt nicht unter `/vote/`. Damit ist `demockrazy` auch ein `testpath`.
      **Liest aus der Datenbank statt nur 200 zu liefern:** ein nackter 200 sagt „uwsgi lebt und die
      URLconf importiert" – und genau das ist nicht, was hier schiefgeht. Die Datenbank ist eine
      SQLite-Datei unter `/var/lib/demockrazy`, auf die der Dienst aus dem read-only Store zugreift;
      steht der Pfad nach einem Deploy falsch, liefert jede Seite einen 500, während ein statischer
      Endpunkt „gesund" meldet.
      **Kein Schreibtest**, obwohl Schreibbarkeit das ist, was die Stimmabgabe braucht: das hieße bei
      jedem Poll schreiben, und mit 4 uwsgi-Prozessen auf einer SQLite-Datei (B13) wäre der
      Health-Check dann selbst eine Ursache der Lock-Fehler, die er melden soll.
      Der 503-Body sagt nur `database unavailable` – der Endpunkt ist unauthentifiziert und der Text
      einer Datenbank-Exception enthält den Dateipfad; der Grund geht ins Log, ein Test prüft, dass
      der Pfad nicht in der Antwort landet.
      **Dabei gefunden: B16** (siehe unten) – die Gegenprobe zu `non_atomic_requests` schlug fehl.
      ⚠️ **Für den Deploy:** das Monitoring muss einen `Host`-Header schicken, der in
      `ALLOWED_HOSTS` steht (Prod: `["wahlcomputer.mayflower.de"]`). Eine Probe gegen
      `localhost` bekommt sonst einen 400 und sieht wie ein Ausfall aus. Gehört ins Modul, nicht
      hierher (Regel 5).

**B16 – `ATOMIC_REQUESTS` war seit 2016 wirkungslos.** *(neu gefunden bei 5.5)*
`demockrazy/settings.py` hatte ein **modulweites** `ATOMIC_REQUESTS = True`, eingeführt in
`154e5f6` (2016-06-09) direkt unter `DATABASES`. Django liest die Option **pro Datenbank**, aus
`DATABASES['default']['ATOMIC_REQUESTS']` – ein modulweiter Name wird nie gelesen. Gemessen statt
geschlossen: `connections.settings['default']['ATOMIC_REQUESTS']` ist `False`, mit `settings.py`
wie mit `test_settings.py`. Produktion hätte den Wert ohnehin verloren, weil `demockrazy_config`
`DATABASES` komplett neu setzt.
**Entfernt statt an die richtige Stelle verschoben** – Einschalten wäre eine echte
Verhaltensänderung in der riskantesten Richtung (jeder Request eine Transaktion auf einer
SQLite-Datei, die 4 Prozesse teilen). Ob das gewollt ist, entscheidet der User → **F18**.
**Nichts hing daran:** `create_poll()` und der `atomic()`-Block in `vote()` sagen es explizit, und
ihre Rollback-Tests waren grün, *während* die Option nichts tat – das ist der Beleg, dass das
Entfernen verhaltensneutral ist. Festgehalten in
[demockrazy/tests/test_transactions.py](../demockrazy/tests/test_transactions.py).
Korrigiert hat der Befund außerdem drei Aussagen: die Begründung von **B7**, die
Risikoeinschätzung von **B13** und die Notiz zu **3.5** („im Request redundant").

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

## 11. Ziel 2 (Batch-Modus für Mails) – ✅ **gebaut**

Diese Liste war die Vorarbeit, solange die Spec fehlte. Sie ist jetzt das Protokoll: was verlangt war,
wie es eingelöst wurde, und wo die Umsetzung von der Planung abweicht. Der Versand selbst steht in
**§11.7** samt Messungen, die Abweichungen in **§11.7a**.

1. ~~**Mail-Versand ist eine aufrufbare Service-Funktion**~~ ✅ mit 3.4 erledigt, mit §11.7
   eingelöst: `mail.poll_created_messages()` rendert, `mail.enqueue()` reiht ein,
   `mail.send_pending()` verschickt getaktet. **`deliver()` gibt es nicht mehr** -- es war genau die
   Stelle, die der Batch-Versender laut diesem Punkt ersetzen sollte, und das Rendern ist unberührt
   geblieben.
2. ~~**Kein SMTP im Request-Zyklus / nicht in der Transaktion**~~ ✅ -- **anders eingelöst als
   3.4 vorsah, und stärker.** Das `on_commit` ist entfallen: eingereiht wird **in** derselben
   Transaktion wie die Tokens, verschickt in einem **anderen Prozess**, der nur committete Zeilen
   sieht. Damit *kann* keine Mail vor ihrem Token rausgehen -- B7 hält strukturell statt über einen
   Callback. Im Request findet überhaupt kein SMTP mehr statt.
3. ~~**Mail-Inhalte als Django-Templates**~~ ✅ mit 3.4 erledigt – liegen unter
   `vote/templates/vote/mail/`, Autoescaping aus, Wortlaut per Test festgenagelt.
4. **Zustand pro Empfänger – F8 ist entschieden: "lieber anonymer".** Damit gilt: **kein dauerhafter
   Zustellstatus pro Adresse**, und der Ersteller bekommt allenfalls Summen ("97 von 100 verschickt"),
   keine Adressliste. Was daraus folgt, ist nicht trivial und sollte vor der Implementierung gelesen
   werden:

   **Ein Versender mit Taktung und Retry muss Adresse und Token zusammen halten, bis zugestellt ist** –
   der gerenderte Mailtext *enthält* den Token. Heute existiert diese Paarung nur im RAM, für die
   Dauer eines Requests. Bei Taktung über Minuten (siehe unten) landet sie auf der Platte, sonst
   verliert ein Neustart mitten im Versand die restlichen Mails, ohne dass jemand sagen kann, welche.

   **Wie groß die Einbuße wirklich ist, lohnt genau hinzusehen:** die Tokens liegen *schon heute*
   vollständig in `vote_token`. Neu wäre allein die Zuordnung "welcher Token gehört zu welcher
   Adresse". Wer die während des Versandfensters lesen kann, erfährt **wer eingeladen wurde** und
   könnte mit Schreibzugriff in dessen Namen abstimmen. Was er **nicht** erfährt, ist **wie jemand
   gestimmt hat** – der Token wird bei der Stimmabgabe gelöscht, und die Stimme trägt keine Kennung.
   **Das Kernversprechen bleibt also unberührt**; preisgegeben wäre eine *temporäre Einladungsliste*.

   Vorschlag entsprechend "lieber anonymer", zu bestätigen wenn die Spec kommt:
   Queue-Zeile trägt nur `(Empfänger, Betreff, Text, Versuche)` – **keine Poll-Kennung**, damit die
   Zeile für sich nicht sagt, um welche Abstimmung es geht; **Löschen bei Erfolg**, nicht als
   "zugestellt" markieren; **keine Historie**; Fortschritt nur als Zahl. Damit ist die Paarung
   zeitlich begrenzt statt dauerhaft, und nach dem Versand ist der Zustand wieder wie heute.
5. ~~**Missbrauchsschutz vor Skalierung** (B4)~~ ✅ mit 3.8 erledigt – Deckel bei 150.
6. ✅ **Gemeinsame SMTP-Verbindung** – vorgezogen, weil es an keiner Spec hängt. `deliver()` baut
   eine Verbindung für die ganze Umfrage statt eine pro Mail. Gemessen über die echte View mit
   einem zählenden Backend: **101 Nachrichten in 101 Verbindungen → 101 Nachrichten in 1**.
   **Ausdrücklich nicht die Kur:** gedrosselt werden Nachrichten, nicht Verbindungen, und deren
   Zahl bleibt gleich. Es verkürzt nur die Wartezeit, die der Ersteller heute synchron aussitzt.
7. **Taktung: vom User vorgegeben (2026-08-04) – „30er Batches mit 2 Sekunden Verzögerung".**
   Ausgearbeitet in §11.7. Offen bleibt **F20** für die genaue Fensterlänge; die zwei Zahlen werden
   deshalb konfigurierbar, mit den Wünschen des Users als Default.
8. Noch offen, sobald die restliche Spec da ist: **Bounce-Handling** und die
   **Fortschrittsanzeige** – letztere ist durch F8 schon eingeschränkt auf Summen ohne Adressliste.

### 11.7 Der getaktete Versand – ✅ **gebaut** (2026-08-04)

**Die Vorgabe des Users (2026-08-04, dreimal bestätigt): 30er Nachrichten-Batches mit 2 Sekunden
Intervall.** Das ist die Taktung, die gebaut wird. Die Rechnung dazu gehört aber daneben:

| | Nachrichten in der ersten Minute |
|---|---|
| 30er Batches, 2 s Pause | 100 Empfänger in ~7 s ⇒ **alle 101** |
| gemessen als immer erfolgreich | **30** |
| gemessen als Fehler (`450`) | 50 |

⚠️ **Wenn das Zählfenster 60 s ist** – der Postfix-Default für `anvil_rate_time_unit`, und genau das
ist **F20** – dann bringt eine 2-Sekunden-Pause zwischen den Batches den `450` an derselben Stelle
zurück, weil sie die *Zahl der Nachrichten pro Minute* kaum senkt. Die Pause, die zur Messung passt,
wäre eine **Fensterlänge** zwischen den Batches: 30 Nachrichten, 60 s Pause, 30 Nachrichten.

**Warum die Vorgabe trotzdem tragbar ist und ich sie so baue:** der `450` ist ein 4xx, also
temporär, und der Entwurf unten **wiederholt** ihn. Es geht dadurch keine Einladung verloren – es
kostet Logzeilen und Wartezeit. Und **beide Zahlen sind Einstellungen**, keine Konstanten:
`DEMOCKRAZY_MAIL_BATCH_SIZE=30` und `DEMOCKRAZY_MAIL_BATCH_PAUSE=2`, mit den Wünschen des Users als
Default. Tauchen die `450` im Log auf, ist die Kur **eine Zahl** und kein Deploy von Code.

**1. Raus aus dem Request – der einzige Punkt ohne Alternative.**
Bei 2 s Pause dauert der Versand nur Sekunden, das würde ein Request noch aushalten. Sobald die
Pause aber auf Fensterlänge hoch muss, sind es Minuten, und `proxy_read_timeout` (nginx) und
`harakiri` (uwsgi) schneiden vorher ab. Der Versand gehört deshalb **von Anfang an** in einen eigenen
Prozess – damit die Pause eine Zahl bleibt und nicht wieder eine Architekturfrage wird.

**2. Die Warteschlange – ihre Form kommt aus F8, nicht aus Bequemlichkeit.**
Ein Modell `OutgoingMail` mit `recipient`, `subject`, `body`, `attempts`. **Keine Poll-Kennung**
(§11.4): die Zeile soll für sich nicht sagen, um welche Abstimmung es geht. **Löschen bei Erfolg**,
kein `sent`-Flag, keine Historie; Reihenfolge über die ID, damit die Einladungsfolge erhalten bleibt.
⚠️ **Was die Taktung an F8 kostet, und das ist neu:** heute lebt die Paarung Adresse↔Token nur im
RAM eines Requests. Mit einer Warteschlange liegt sie **auf der Platte** – bei 2 s Pause für
Sekunden, bei 60 s für Minuten. Genau die Einbuße, die §11.4 vorhergesehen hat. Preisgegeben wäre
*wer eingeladen wurde*, **nicht wie jemand gestimmt hat**; das Kernversprechen bleibt unberührt.

**3. Einreihen atomar mit den Tokens.**
`create()` rendert wie heute und schreibt die Zeilen **in derselben Transaktion** wie `create_poll()`.
Sonst kann ein Absturz dazwischen Tokens ohne Einladung hinterlassen – Wähler, die ihren Token nie
erfahren, und eine Umfrage, die nur noch der Ersteller schließen kann. Das `on_commit(deliver)` aus
3.4 entfällt damit; seine Zusage („keine Mail raus, bevor die Tokens durabel sind", B7) erfüllt die
Warteschlange strukturell, weil der Versender in einem anderen Prozess läuft und nur committete
Zeilen sieht.

**4. Der Versender: ein Management-Command, kein Daemon.**
`manage.py send_pending_mails`, und in dieser Reihenfolge:

- **Sperre zuerst** – `flock` auf eine Datei neben der Datenbank. Läuft schon ein Versand, beendet
  sich der zweite sofort und still. Damit braucht die Tabelle **keine Claim-Spalte**, und ein Timer,
  der in einen laufenden Versand feuert, tut nichts Schädliches.
- `batch_size` Zeilen nach ID nehmen, über **eine** SMTP-Verbindung verschicken (steht seit 11.6),
  jede erfolgreiche Zeile löschen.
- `pause` Sekunden warten, nächster Batch, bis die Warteschlange leer ist oder ein Laufzeitbudget
  erschöpft ist.
- **Beim ersten 4xx den Lauf abbrechen**, nicht weiterprobieren: ein `450` heißt „du bist über dem
  Limit", die nächsten 29 bekämen ihn auch und würden nur `attempts` verbrennen. Der Timer versucht
  es beim nächsten Intervall erneut.
- Ein 5xx ist dauerhaft: `attempts` hoch, nach N Versuchen Zeile löschen und protokollieren –
  **ohne Adresse**, wie `deliver()` das heute schon tut (F8).
- `VOTE_SEND_MAILS=False` druckt statt zu verschicken, genau wie `deliver()` heute.

**4a. Blockiert der schlafende Versender die Abstimmung? Gemessen: nein – unter einer Bedingung.**
Er läuft in einem eigenen Prozess, schreibt aber in **dieselbe SQLite-Datei** wie die vier
uwsgi-Prozesse, und die steht seit 5.4 auf `transaction_mode=IMMEDIATE` – die Schreibsperre fällt
schon beim `BEGIN`. Gemessen mit 8 gleichzeitigen Wählern × 25 Stimmabgaben gegen einen laufenden
Versender (3 Batches à 30):

| Versender | Stimmen | `database is locked` | Wartezeit je Stimme (Schnitt / schlimmste) |
|---|---|---|---|
| **A** `sleep` **außerhalb** der Transaktion, Lauf 6 s | 200/200 | 0 | **7 ms** / 0,2 s |
| **A'** dasselbe, Lauf 24 s | 200/200 | 0 | **9 ms** / 0,2 s |
| **B** eine Transaktion um den ganzen Lauf, 6 s | 200/200 | 0 | 253 ms / **6,6 s** |
| **B'** dieselbe Transaktion, Lauf 25 s | **192/200** | **8** | 972 ms / **20,0 s** |

**Die Bedingung ist also präzise benennbar: keine Transaktion darf über eine Pause reichen.** Hält
man sie ein, ist die Länge des Laufs **völlig gleichgültig** (A gegen A': dieselben 7–9 ms). Hält man
sie nicht ein, degradiert es zuerst nur (B: Stimmen dauern Sekunden statt Millisekunden) und wird
dann zum Datenverlust, sobald der Lauf länger dauert als der `timeout` von 20 s – bei B' sind **acht
Stimmen nicht gezählt worden**, und die schlimmste Wartezeit war exakt der Timeout.
*(Meine Vorhersage „B legt die Abstimmung still" war zu grob: bei kurzen Läufen wartet der Wähler
nur, verloren geht nichts. Erst jenseits des Timeouts kippt es.)*
Konkret heißt das für den Command: `sleep` steht zwischen den Batches und **nie** in einem
`atomic()`, und pro Mail gibt es eine eigene kurze Transaktion. Eine bloß *offene* Verbindung ist
unkritisch – SQLite sperrt erst in einer Transaktion.

**4b. Was tatsächlich blockieren kann, ist SMTP – und das ist heute schon so.**
`EMAIL_TIMEOUT` war nicht gesetzt, und Djangos Default ist `None`. Nachgesehen statt vermutet: das
Backend gibt `timeout` dann gar nicht an `smtplib` weiter, `smtplib` nimmt den Socket-Default, und
`socket.getdefaulttimeout()` ist ebenfalls `None` – **ein Server, der die Verbindung annimmt und dann
schweigt, blockiert unbegrenzt.** Heute hängt daran ein uwsgi-Prozess (der Versand läuft synchron im
Request), und es gibt vier davon. Für den Versender wäre es schlimmer: er sperrt sich selbst, ein
Lauf ohne Ende hält die Sperre, und dann geht **gar keine** Mail mehr raus.
✅ **Deshalb vorgezogen und schon gesetzt:** `EMAIL_TIMEOUT = 10` (über `DEMOCKRAZY_MAIL_TIMEOUT`
konfigurierbar), mit einem Test, der die Endlichkeit festhält. Dazu gehört später ein Laufzeitbudget
im Command, damit ein Lauf sich auch dann beendet, wenn jede einzelne Verbindung brav in 10 s
scheitert.

**5. Idempotenz: verschicken, dann löschen.**
Zwischen SMTP-Erfolg und `DELETE` kann der Prozess sterben, dann geht die Mail doppelt raus.
**Absichtlich diese Richtung:** die zweite Mail trägt denselben Token, und der ist einmalig – eine
doppelte Einladung ist harmlos, eine doppelte Stimme dadurch unmöglich. Der umgekehrte Fehler
(löschen, dann verschicken) **verliert** eine Einladung, und dann fehlt ein Token für immer: die
Umfrage schließt nicht mehr von selbst.

**6. Was das im Deployment kostet – und was nicht.**
Ein systemd-Timer, der den Command aufruft. **Kein Broker, kein Daemon, kein zusätzliches Paket.**
Für hundert Mails im Minutentakt ist ein Timer genug, und die Datenbank ist schon da.
→ [to-check.md](to-check.md) §C5. Warum nicht etwas Fertiges: siehe 6a, das ist nachgesehen worden.

**6a. Hat Django selbst eine Queue? Nachgesehen, nicht erinnert – und es korrigiert eine Annahme.**

*Was ich vorher geschrieben hatte: Celery und `django-tasks` bräuchten „ein Paket, das erst in der
nixpkgs liegen muss". **Das war falsch.** In der gepinnten nixpkgs liegen alle: `django-tasks` 0.12.0,
`celery` 5.6.3, `huey` 2.6.0, `django-q2` 1.9.0, `rq` 2.8, `django-rq` 4.1, `kombu`, `redis`,
`django-celery-beat`. Das Verpackungsargument gibt es nicht.*

Die Antwort auf die eigentliche Frage:

- **Django 5.2.15 – das, was hier läuft – hat keine Queue.** Im installierten Baum nachgesehen: kein
  `django.tasks`, keine Datei mit `task` oder `queue` im Namen, kein Setting mit `TASK`, `QUEUE`,
  `WORKER` oder `BROKER`. Das Nächstgelegene ist `transaction.on_commit()` – ein Callback beim
  Commit, im Prozess, **nicht persistiert**, seit 3.4 in Benutzung – und der Cache. Keins von beidem
  übersteht einen Neustart.
- **Django 6.0.6 hat `django.tasks`** (liegt in derselben nixpkgs). Aber: `TASKS` steht per Default
  auf `django.tasks.backends.immediate.ImmediateBackend`, und es gibt **genau zwei** Backends,
  `Immediate` und `Dummy`. `Immediate` ruft die Funktion **sofort und im selben Prozess** auf
  (`task.call(...)`), `Dummy` merkt sie sich und führt sie nie aus. **Kein Datenbank-Backend, kein
  Worker, kein Management-Command dafür** – die Commandliste von 6.0.6 enthält nichts in der
  Richtung. `django.tasks` normiert also, *wie man eine Aufgabe deklariert und einreiht*; wer sie im
  Hintergrund ausführt, ist ausdrücklich nicht dabei (so ist DEP 0014 gestaffelt).
- **`django-tasks` 0.12.0** ist dasselbe Bild – die Referenzimplementierung, und sie enthält nur
  `Immediate` und `Dummy`, keine Migrations, keinen Worker. `ImmediateBackend` deklariert nicht
  einmal `supports_defer`, das `run_after`-Feld am Task ist dort also wirkungslos.

**Folgerung, jetzt mit dem richtigen Grund:** ein fertiger Baustein, der die Arbeit abnimmt, existiert
nicht. Mit `django.tasks` hätte man die API und müsste Tabelle, Versender, Zeitsteuerung **und** ein
eigenes Backend darunter schreiben – mehr Arbeit als der Entwurf oben, nicht weniger. Celery und RQ
brauchen weiterhin einen **Broker als zusätzlichen Dienst** auf der Node; `huey` mit SQLite-Storage
käme ohne Broker aus, verlangt aber einen **dauerhaft laufenden Consumer** und eine zweite
Datenbankdatei. Für 101 Mails ist ein Timer plus die vorhandene Tabelle das Kleinere.
**Was `django.tasks` trotzdem wert ist:** als *Form* zum Nachbauen. Wer den Versender so schneidet,
dass „einreihen" und „ausführen" getrennt bleiben, kann später auf ein Backend umstellen, ohne die
Aufrufstellen anzufassen. Der Entwurf oben tut das schon – `enqueue` in `create()`, Ausführung im
Command.
⚠️ Ein Wechsel auf **Django 6** wäre ohnehin eine eigene Entscheidung: 5.2 ist LTS, 6.0 nicht, und
die Version kommt aus der nixpkgs des Colmena-Flakes (§1).

**6b. Der User bleibt auf der LTS (Entscheidung 2026-08-04). Welche Optionen bleiben dann?**

**Alle.** Das ist der Kern: Django 6 hätte hier nichts beigetragen, was 5.2 fehlt – `django.tasks` hat
auch dort **kein Datenbank-Backend und keinen Worker** (6a). Die LTS-Entscheidung streicht also keine
einzige Möglichkeit; sie schließt nur die *Aussicht* auf ein künftiges Core-Backend aus, und das gibt
es noch nicht.

Was auf 5.2 zur Wahl steht, gegen **dieses** Deployment gerechnet (SQLite, vier uwsgi-Prozesse,
NixOS-Modul außerhalb des Repos, ~101 Mails pro Umfrage):

| | Zusätzliche Abhängigkeit | Zusätzlich auf der Node | Taktung | Einreihen atomar mit den Tokens |
|---|---|---|---|---|
| **A** eigene Tabelle + Command + Timer (§11.7) | keine | **ein systemd-Timer** | selbst, exakt wie vorgegeben | **ja** |
| **B** A, aber über die `django-tasks`-API deklariert | `django-tasks` 0.12 (gepackt) | derselbe Timer | selbst (Immediate/Dummy können kein `run_after`) | ja |
| **C** `django-q2` – Queue in der ORM-Datenbank | `django-q2` 1.9.0 (gepackt) | **dauerhafter `qcluster`-Daemon** | selbst | ja |
| **D** `huey` mit SQLite-Storage | `huey` 2.6.0 (gepackt, Django-Anbindung eingebaut) | **dauerhafter Consumer** + zweite DB-Datei | selbst | nein (eigener Store) |
| **E** Celery + Redis | `celery` 5.6.3, `redis` (gepackt) | **Redis als Dienst** + Worker-Daemon | **eingebaut**: `rate_limit="30/m"` | nein (Broker) |
| **F** fertige Mail-Queue (`django-mailer`, `django-post-office`) | **nicht in der nixpkgs** | – | teils eingebaut | ja |

Drei Befunde, die die Wahl entscheiden, und alle drei sind nachgesehen:

- **F fällt an der Verpackung aus.** `django-mailer`, `django-post-office`, `django-mail-queue`,
  `procrastinate`, `django-tasks-database` – **keins liegt in der gepinnten nixpkgs.** Hier greift das
  Argument, das ich in 6a fälschlich gegen Celery erhoben hatte: das wäre echte Paketierungsarbeit im
  Repo des Users.
- **C schreibt dauernd in genau die Datei, um die 5.4 sich gekümmert hat.** Ein `qcluster` pollt die
  Datenbank; das ist zusätzlicher Schreibverkehr auf der SQLite-Datei, die vier uwsgi-Prozesse teilen
  (B13). Der Entwurf A schreibt nur, wenn wirklich eine Mail rausgeht.
- **E ist funktional der beste Treffer und der teuerste Umbau.** Celerys `rate_limit` ist genau die
  Zusage, die hier gebraucht wird, und man müsste sie nicht selbst schreiben. Der Preis ist ein
  **zusätzlicher Dienst (Redis)** plus ein Worker-Daemon auf einer Node, die heute nginx und ein
  uwsgi fährt – für 101 Mails.

**Und eine Idee, die naheliegt und nachweislich nicht funktioniert:** Djangos eingebautes
`filebased.EmailBackend` als Spool zu benutzen. Es klingt perfekt – keine Migration, kein Modell,
nichts in der Datenbank. Nachgesehen: es schreibt **alle Nachrichten einer Verbindung in *eine*
Datei**, aneinandergehängt und durch eine Zeile aus `-` getrennt, benannt nach Zeitstempel. Das ist
ein Protokoll, keine Warteschlange – eine Datei je Nachricht gibt es nicht, und ein Dateilauf wäre
außerdem **nicht** Teil der Token-Transaktion.

**Empfehlung: A.** Ein Modell, ein Command, ein Timer, keine Abhängigkeit, und die Taktung ist genau
die vorgegebene. B lohnt nur, wenn Vorwärtskompatibilität zu einem künftigen Core-Backend wichtiger
ist als weniger Code – man bekommt die API und schreibt alles darunter trotzdem. C, D und E lohnen
erst, wenn es **weitere** Hintergrundaufgaben geben soll; für diese eine ist ein Daemon oder ein
Broker mehr Betrieb als Nutzen.
**Timer-Intervall: eine Minute.** Der Preis ist ehrlich zu benennen: die erste Einladung geht bis zu
eine Minute nach dem Anlegen raus, die Mail an den Ersteller auch. Das ist der Gegenwert dafür, dass
nichts mehr im Request hängt.

**7. Fortschritt: ein Satz auf der Manage-Seite.** ✅ **gebaut, aber anders als hier geplant.**
Der Plan sagte „n Einladungen noch nicht verschickt". **Das lässt F8 nicht zu, und das ist beim Bauen
erst aufgefallen:** eine Warteschlangenzeile trägt bewusst keine Poll-Kennung, es gibt also keinen
Weg, sie *dieser* Umfrage zuzuordnen. Einen zu bauen wäre genau der Bezug, auf den §11.4 verzichtet
hat – auch über eine indirekte Kennung, denn wer die Warteschlange lesen kann, kann auch `vote_poll`
lesen.

Gebaut ist deshalb die eine Richtung, die **logisch sicher** ist: *ist die Warteschlange leer, sind
die Einladungen dieser Umfrage sicher raus.* Umgekehrt gilt nur „irgendwas wartet noch", und genau so
steht es auch da:

| Warteschlange | Text auf der Manage-Seite |
|---|---|
| leer | „No invitations are waiting to be sent." |
| nicht leer | „Invitations are still queued for sending." |

**Und `exists()` statt `count()`**: eine Zahl wäre eine Aussage über das Versandvolumen *anderer*
Umfragen, und die Manage-Seite ist ohne Token erreichbar. Ein Bit ist alles, was der Ersteller
braucht – die Frage lautet „sind die Mails raus", nicht „wie viele".

Damit ist der Punkt kleiner als versprochen, und das ist eine Folge von F8, kein Versäumnis. Wer den
per-Umfrage-Fortschritt doch will, entscheidet damit F8 neu.

**8. Migration `0004`** – eine **neue** Tabelle. Additiv, und anders als `0003` schreibt SQLite dafür
keine bestehende Tabelle neu.

### 11.7a Was beim Bauen anders kam als im Entwurf

Der Entwurf hat gehalten. Vier Dinge sind beim Umsetzen präziser oder anders geworden, und sie lohnen
je zwei Zeilen:

1. **Der Umgang mit Fehlern ist feiner als „4xx anhalten, 5xx verwerfen".** Dazwischen liegt ein
   dritter Fall, und er ist der wichtigste: **der Server war gar nicht erreichbar.** Dann hat er über
   *diese* Nachricht nichts gesagt, also darf sie auch keinen Versuch verbrauchen -- sonst würde ein
   einstündiger Ausfall die Einladungen der Reihe nach wegwerfen, eine pro Timer-Aufruf. Verbindungs-
   und Timeout-Fehler brechen den Lauf deshalb ab, **ohne** `attempts` zu erhöhen. Nur eine aktive
   Absage des Servers für genau diese Nachricht zählt.
2. **Eine Verbindung pro Batch, nicht eine pro Lauf.** Die Pause soll nicht in einer offenen
   Verbindung verbracht werden, und die Batchgrenze ist der natürliche Ort dafür. 101 Mails kosten
   damit 4 Verbindungen statt 1 -- gegenüber den 101 von vorher ist das kein Thema, und es ist
   robuster, sobald die Pause auf Fensterlänge steigt.
3. **`5xx` wird sofort verworfen statt nach N Versuchen.** Ein 5xx ist per RFC dauerhaft; „User
   unknown" fünfmal zu wiederholen hilft niemandem. `MAX_ATTEMPTS` gilt damit nur noch für den
   4xx-Fall.
4. **Ein Zählfehler im ersten Entwurf, gefunden beim Schreiben:** die Restmenge wurde pro Zeile
   mitgebucht, wobei kumulative Summen gegen die Größe *eines* Batches gerechnet wurden -- falsch,
   sobald es mehr als einen Batch gab. Jetzt wird am Ende einmal gezählt.

**Gemessen, mit den Zahlen des Users, gegen eine echte Datenbank:**

| | Ergebnis |
|---|---|
| 100 Empfänger anlegen | **101 Zeilen** in der Warteschlange, 100 Tokens, **0 Mails im Request** |
| Felder einer Zeile | `id, recipient, subject, body, attempts` -- **keine Poll-Kennung, kein Zeitstempel** |
| ein Lauf `send_pending_mails` | 101 verschickt, 0 aufgegeben, 0 warten noch, **4 Batches in 7,2 s** |
| zweiter Aufruf während eines laufenden | *„Es läuft schon ein Versand, dieser Aufruf tut nichts."* -- der erste liefert danach vollständig ab |

Die 7,2 s sind die Rechnung aus §11.7 in echt: vier Batches, drei Pausen à 2 s, der Rest Arbeit.
**Und sie sind zugleich die Bestätigung der Warnung dort:** alle 101 Nachrichten liegen damit im
selben Zeitfenster. Wenn `smtp.mayflower.de` mit 60 s zählt, kommt der `450` -- dann ist
`DEMOCKRAZY_MAIL_BATCH_PAUSE=60` die Antwort, und der Lauf dauert ~3,5 Minuten statt 7 Sekunden.

---

### Das Problem, das Ziel 2 lösen soll – jetzt gemessen statt vermutet

**Der Mailserver drosselt, und zwar nach Nachrichten pro Zeitfenster.** Vom User geliefert (2026-08-04),
aufgetreten bei **50 Mails** in Produktion:

```
Unfortunately, the following errors were encountered while dispatching mails.
(450, b'4.7.1 Error: too much mail from ...
```

Was daran wichtig ist:

- **`450` ist ein 4xx, also temporär.** Das Protokoll sieht „später nochmal" vor – Wiederholung ist
  die vorgesehene Antwort, nicht ein Workaround.
- **Die Formulierung „too much mail from" ist die des Postfix-*Message*-Rate-Limits**
  (`smtpd_client_message_rate_limit`). Es zählt **Nachrichten pro Client und Zeitfenster** (Default
  60 s), **nicht Verbindungen**. Der genaue konfigurierte Wert ist noch nicht bekannt → **F20**.
- Reale Umfragen haben 60–100 Empfänger (F13). Die Grenze liegt also *mitten* im Normalbetrieb.

**Gemessen am eigenen Code:** `deliver()` ruft `send_mail()` **pro Empfänger** auf, und jeder Aufruf
baut eine eigene SMTP-Verbindung auf. Nachgezählt mit einem zählenden Backend: 100 Empfänger ⇒
**101 Nachrichten in 101 Verbindungen**. Bei 150 ms pro Verbindung (TCP + STARTTLS + AUTH) sind das
~16 s, mit einer gemeinsamen Verbindung ~1,2 s – **Faktor 14**.

**Korrektur einer eigenen Vermutung:** ich hatte zuerst geschlossen, eine gemeinsame Verbindung
(`get_connection()` + `send_messages()`) behebe das Problem. **Tut sie nicht** – gedrosselt werden
Nachrichten, nicht Verbindungen, und deren Zahl bleibt gleich. Sie bleibt trotzdem lohnend (14×
schneller, ein AUTH statt hundert) und ist der billigste erste Schritt, aber **die Kur ist Taktung
über Zeit plus Wiederholung der 450er.**

**Und der Versand läuft heute synchron im Request.** `transaction.on_commit()` verschiebt ihn nicht:
ohne offenen `atomic`-Block führt Django den Callback **sofort** aus, und einen solchen Block gibt es
seit B16 nicht mehr um den Request. Gemessen: die POST-Antwort kommt erst, wenn alle Mails durch sind.
Für getaktetes Senden über Minuten heißt das zwingend: **raus aus dem Request** – Management-Command
plus Queue. Was `on_commit` leistet, bleibt richtig und wichtig (keine Mail vor dem Commit der
Tokens), es ist nur keine Entkopplung.

⚠️ **Vor dem Deploy zu wissen:** die Fehlerliste, mit der der User oben diagnostiziert hat, kommt aus
`create.html` an `master` – also aus dem *heute* laufenden Code. **3.4 hat sie entfernt** (bewusst,
Änderung (a) dort): der Versand läuft nach dem Commit, die Seite ist dann schon gerendert. Nach dem
Deploy stehen diese Fehler **nur noch im Log**. Genau das ist das stärkste Argument für einen echten
Zustellbericht – und der braucht die Entscheidung aus **F8** (Anonymität).

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
| **F20** | **Wie hoch ist das Rate-Limit von `smtp.mayflower.de`?** Gebraucht wird der konfigurierte Wert von `smtpd_client_message_rate_limit` (bzw. was eine Policy dort setzt) und die Länge des Zeitfensters (`anvil_rate_time_unit`, Default 60 s) – dazu die **vollständige** Fehlerzeile, weil der abgeschnittene Teil hinter *from* sagt, worauf gezählt wird (Client-IP oder Absenderadresse). **Eingegrenzt vom User: 30 gingen immer durch, bei 50 kam der 450er** – die Grenze liegt also zwischen 30 und 50 pro Fenster. Davon hängen Batch-Größe und Pause ab; für eine belastbare Taktung fehlt der genaue Wert. | **Ziel 2** |
| **F15** | **Teilweise beantwortet.** Der Proxy liegt vor: `forceSSL` + HSTS + FrameOpts/GeneralProtect-Snippets, CSP definiert aber nicht eingebunden (Analyse in [deployment.md](deployment.md)). Damit sind `SECURE_SSL_REDIRECT` und `SECURE_HSTS_SECONDS` **gegenstandslos**. **Es fehlt noch:** `services.nginx.recommendedProxySettings` auf dem Proxy-Host und der vollständige `proxyPass` – daran hängt, ob `X-Forwarded-Proto` ankommt, und damit die Auflösung des CSRF-Rätsels. | 2.7 |
| ~~F12~~ | ~~Prod-Schema-Stand?~~ → **geliefert.** Prod hat zwei Migrations (2016), DB liegt unter `/var/lib/demockrazy/db.sqlite3`. Ausgewertet in [notes/phase-2-migrations.md](phase-2-migrations.md). **Kleiner Rest inzwischen erledigt:** `PRAGMA table_info(vote_poll)` auf Prod bestätigt `type varchar(20) NOT NULL` an Position 8 und die Spaltenreihenfolge der zwei rekonstruierten Migrations. | – |
| ~~F4~~ | ~~Highcharts-Lizenz oder ersetzen?~~ -> **ersetzen, Chart.js (MIT).** Umgesetzt in 4.3. | – |
| ~~F5~~ | ~~Zugangsschutz für Poll-Erstellung?~~ -> **Deckel auf die Empfängerzahl, kein IP-Rate-Limit.** Umgesetzt in 3.8, Wert 150. | – |
| ~~F8~~ | ~~Anonymität vs. Zustellstatus pro Empfänger?~~ -> **"lieber anonymer".** Kein dauerhafter Status pro Adresse, keine Adressliste für den Ersteller. Was daraus für die Queue folgt – und wie klein die Einbuße tatsächlich ist – steht in §11.4. | – |
| **F17** | **Überschreibt das NixOS-Modul einen der vier Mail-Text-Settings?** 3.4 hat `VOTE_MAIL_SUBJECT`, `VOTE_MAIL_TEXT`, `VOTE_ADMIN_MAIL_SUBJECT`, `VOTE_ADMIN_MAIL_TEXT` aus `settings.py` entfernt – der Text kommt jetzt aus Templates. Setzt `demockrazy_config` (oder die `djangoSettings`-Option) einen davon, wird der Wert nach dem Deploy **stillschweigend ignoriert** und Prod verschickt den Repo-Wortlaut. Prüfung im Repo des Users: `grep -rn 'VOTE_MAIL\|VOTE_ADMIN_MAIL\|VOTE_BASE_URL\|VOTE_MAIL_FROM'`. Meine Modul-Analyse in [deployment.md](deployment.md) listet keinen dieser vier, und die alte `local_settings.py` überschrieb nur `VOTE_BASE_URL`/`VOTE_MAIL_FROM`/`VOTE_SEND_MAILS` – die drei sind bewusst geblieben. Trifft die Annahme nicht zu, gehört der Text ins Template. | **vor dem Deploy** |
| ~~F13~~ | ~~Wie groß sind Abstimmungen real?~~ -> **60–100 Empfänger pro Umfrage.** Damit genügt SQLite mit WAL + `timeout`, **kein Postgres** (5.4). Und der Kern der Antwort: **ab ~40–50 scheitert der Massenversand heute** – das ist das Problem, das Ziel 2 lösen soll, siehe §11. | – |
| ~~F19~~ | ~~Bootstrap 5 vendoren – Freigabe und Quelle?~~ → **freigegeben, GitHub-Release-Dist.** Umgesetzt in 4.1: v5.3.8, nur `bootstrap.min.css` + `bootstrap.bundle.min.js`, ohne Maps. Herkunft und Checksummen in [PROVENANCE.md](../vote/static/bootstrap-5.3.8-dist/PROVENANCE.md). | – |
| ~~F18~~ | ~~Soll `ATOMIC_REQUESTS` tatsächlich an?~~ -> **nein**, und nicht aus Geschmack: gemessen, dass es die Teilstimme aus `vote()` **nicht** zurückrollen würde. `vote()` fängt den `KeyError` selbst und liefert eine 200-Seite – für Django ein erfolgreicher Request, also Commit; zurückgerollt würde nur bei einer durchgereichten Exception. Der explizite Block leistet hier also etwas, das `ATOMIC_REQUESTS` nicht kann, während Anschalten die Schreibsperre über den ganzen Request halten würde (B13). Messung in [demockrazy/tests/test_transactions.py](../demockrazy/tests/test_transactions.py). | – |
| ~~F16~~ | ~~Sind die drei Verschärfungen aus 3.1 gewollt?~~ → **ja**, vom User bestätigt (alle sechs Felder Pflicht, Djangos Adressvalidator, `title` auf 200 Zeichen). Seit 3.2 in der View wirksam. | – |

---

## 14. Phase 7 – Umfassendes Review

> **7.1 gelaufen und 7.2 abgearbeitet** (freigegeben am 2026-08-04). Befunde, Negativraum und das
> Ergebnis je Befund stehen in [review.md](review.md), Sonden in
> [review_probes.py](review_probes.py), Punkte außerhalb des Repos in [to-check.md](to-check.md)
> (neu aus dem Review: A4, A5, D5, D6).
>
> **24 Befunde** -- 1 kritisch, 2 hoch, 6 mittel, 8 niedrig, 7 Notiz. **22 sind behoben**, in 13
> Commits mit der Nummer im Betreff. **R2-1 ist nachgezogen**, nachdem der User bestätigt hat, dass
> es in Produktion ein Staff-Konto gibt: `Choice.votes` ist nicht mehr editierbar und Tokens sind
> nicht mehr lesbar; dazu beschränkt der User `/admin/` am Proxy aufs Intranet, womit das fehlende
> Login-Rate-Limit gegenstandslos ist. Offen bleiben **R8-1** (der User prüft das SMTP-Kennwort vor
> dem Deploy) und **R9-3** (Verfahrenshinweis beim Rollback, D5).
>
> Die drei, die zählten:
> **R4-1** (kritisch) zwei gleichzeitige POSTs mit demselben Token ergaben **zwei Stimmen** -- 4 von
> 100 Runden gemessen. Behoben in `a1b5117`, indem die Löschung des Tokens zur Bedingung der Buchung
> wurde; danach **0 von 100**.
> **R5-1** (hoch) ein Zeilenumbruch im Titel machte die erste Warteschlangenzeile unversendbar und
> legte damit den Versand **aller** Umfragen still. Behoben in `af30fa5`, an beiden Enden.
> **R2-1** (hoch) `/admin/` legte Tokens offen und Stimmzahlen editierbar hin, und ein Staff-Konto
> existiert. Behoben in `5adb612`: `votes` `readonly`, Token-Werte aus Liste und Formular heraus.
> **Was noch nicht geprüft ist, steht in review.md §7** -- vor allem die Suite als Text und der
> Branch als Verlauf (Commit für Commit).

- [x] **7.1 Review durchführen.** ✅ Gelaufen; Befunde in review.md §5, Negativraum in §6. Umfang ist **der ganze Branch (`master..HEAD`) *und* der
      Ist-Zustand** – ein Diff zeigt nicht, was jemand hätte ändern müssen und nicht getan hat, ein
      Blick nur auf den Endzustand nicht, was unterwegs eingeschleppt wurde.
      Geprüft wird in dieser Reihenfolge: **Anonymität, Auth, Injection, Nebenläufigkeit,
      Fehlerbehandlung, Informationslecks, Missbrauch/DoS, Geheimnisse, Migrations/Deploy,
      Testqualität, Performance, Lieferkette, Barrierefreiheit, Wartbarkeit, Dokumentation.**
      Das Kernversprechen zuerst, Kosmetik zuletzt.
      **Vier Regeln, die das Review belastbar machen** (Begründung in review.md §2):
      (a) ich habe alles selbst geschrieben, deshalb wird gegen eine **Liste der Fehlerklassen
      gesucht, die in diesem Projekt real vorgekommen sind** (K1–K8 in review.md §3) statt auf
      Einfälle gewartet;
      (b) jeder Befund ist **gemessen oder ausdrücklich als ungemessen markiert**, nie „könnte";
      (c) **keine Reparatur während des Reviews** – wer im Vorbeigehen behebt, verliert den Nachweis
      und hört auf zu suchen;
      (d) **Negativraum wird protokolliert** – ohne „so wurde geprüft, kein Befund" ist das nicht von
      „nicht hingesehen" zu unterscheiden.
      **Die Testsuite ist Prüfgegenstand, nicht Prüfinstanz** – nach K4 (die erste Phase-0-Sonde
      meldete Erfolg auf zwei identischen Tracebacks) ist „die Tests sind grün" kein Argument.
- [x] **7.2 Befunde abarbeiten.** ✅ **22 von 24 behoben**, ein Commit je Befund bzw. Befundpaar mit
      der Nummer im Betreff (`a1b5117` … `9bf0fc7`). Jede Behebung ist gegengeprüft: alter Zustand
      wiederhergestellt, neuer Test gefahren -- ein Test, der auch ohne die Behebung besteht, wäre
      K4. Die Suite ist dabei von 215 auf **253** Tests gewachsen, und alle fünf blinden Flecken der
      Mutationssonde sind zu; nach dem Nachzug von R2-1 sind es **261**.
      **Offen und nicht hier lösbar:** R8-1 (der User prüft das Kennwort vor dem Deploy, A5) und
      R9-3 (Verfahrenshinweis, D5). R2-1 ist zu, sobald die Intranet-Beschränkung für `/admin/`
      am Proxy steht (A4).
      **Eine Zahl braucht deinen Blick:** `VOTE_MAX_CHOICES` = 100 aus R7-1 ist von mir gesetzt, nicht
      von dir -- anders als die 150 für Empfänger.

## 13. Reihenfolge / Abhängigkeiten

```
Phase 0  Baseline, Prod-Fakten                                        ✅
Phase 1  Tooling + Testsuite (das Sicherheitsnetz)                    ✅
Phase 2  Migrations, Django 5.2, Settings                             ✅ außer 2.7 (braucht F15)
Phase 3  Code-Modernisierung                                          ✅ vollständig (3.1–3.9)
Phase 4  Frontend                                                     ✅ vollständig
Phase 5  Deployment & CI                                              ✅ vollständig (5.1–5.5)
Phase 6  Dokumentation                                                ✅ vollständig
Phase 7  Umfassendes Review (§14)                                     ✅ 7.1 gelaufen, 7.2 mit
                                                                        22 von 24 Befunden behoben

offen:
  7.2  Zwei Befunde, die **außerhalb dieses Repos** liegen: R8-1 (SMTP-Kennwort, prüft der User vor
       dem Deploy, A5) und R9-3 (Rollback-Verfahren, D5). Dazu am Proxy die Intranet-Beschränkung
       für `/admin/` (letzter Handgriff zu R2-1, entschieden) und die noch nicht geprüften Teile
       aus review.md §7 -- die Suite als Text und der Branch Commit für Commit.
  2.7  TLS-Hardening – **zum größten Teil gegenstandslos**, seit der Proxy vorliegt: `forceSSL`
       und HSTS stehen dort schon, in Django wären sie doppelt. Es bleibt (a) die Restfrage aus
       **F15** (`X-Forwarded-Proto`, und damit das CSRF-Rätsel), (b) der widersprüchliche
       `X-Frame-Options` (Proxy `sameorigin` vs. Django `DENY` – beide gehen raus), (c) der
       Vorschlag, den vorhandenen CSP-Snippet einzubinden, was erst seit 4.1/4.3 sinnvoll geht.
       **Alle drei betreffen den Proxy, nicht dieses Repo.**

**Ziel 1 ist damit inhaltlich fertig, und das Bug-Register ist leer.** B9 (Token im Query-String)
ist mit 3.9 gefallen – additiv, wie es Regel 4/5 verlangt: der Token zieht beim ersten Aufruf in ein
Cookie um, der Mailtext bleibt unverändert. Was daran nicht im Repo lösbar ist, ist die Logzeile des
einen Aufrufs, der den Link trägt → [to-check.md](to-check.md) §B3.

ZIEL 2 (Batch-Mails) hat eine gemessene Problembeschreibung (§11) und mit **F8** die
Anonymitäts-Entscheidung. Offen: die Spec und **F20** (der genaue Rate-Limit-Wert).

erledigt in Phase 3: 3.1 Forms · 3.2 create()/manage() · 3.3 vote() · 3.4 Mail-Service ·
3.5 Poll-Service · 3.6 Models/Constraints · 3.7 path() · 3.8 Empfänger-Deckel · 3.9 Token-Umzug
  └─ kein `xfail` mehr in der Suite, alle 3 roten Ruff-Befunde ebenfalls weg
  └─ 3.4 ist die Schnittstelle für ZIEL 2 (Batch-Mails, nach Spec)
```

**Nächster Schritt: die zwei offenen Fragen aus [to-check.md](to-check.md), A1 und A5** -- alles andere im
Repo ist abgearbeitet. Wer weiterprüfen will, findet in review.md §7, was der Review-Lauf **nicht**
abgedeckt hat.

**Für Ziel 1 ist im Repo nichts offen.** Was von 2.7 übrig ist, gehört in den Proxy und
braucht F15. Danach ist **Ziel 2** dran – die Problembeschreibung steht in §11, die Anonymitätsfrage
ist mit F8 entschieden, es fehlen die **Spec** und **F20**.
**Alles, was außerhalb dieses Repos zu tun ist, steht in [to-check.md](to-check.md)** – Proxy,
NixOS-Modul, Prod-Node und die offenen Fragen, mit Befehlen und Begründung. **F17** ist der einzige
Punkt davon, der noch eine Antwort braucht.
**Vor dem Deploy:** F17 klären; die Migration `0003` schreibt `vote_poll` und `vote_token` neu
(Details in [phase-2-migrations.md](phase-2-migrations.md)), Backup liegt vor (borg 03:00/04:00).
**Die Vorarbeit für Ziel 2 (§11.1–5) ist vollständig** – ein Batch-Versender ersetzt
`mail.deliver()`, F8 ist entschieden, der Missbrauchsschutz steht. Was fehlt, ist die Spec und F20.
Details in [handover.md](handover.md) §9.
