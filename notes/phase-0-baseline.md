# Phase 0 – Baseline: Ergebnisse

Durchgeführt 2026-08-03 auf Branch `update/modernize-2026`, Code-Stand = Basis-Commit `3074dbb`.
Alle Zahlen unten sind **gemessen**, nicht geschätzt.

---

## 0.1 Versionslage (verifiziert gegen nixpkgs)

| Quelle | Python | Django | Postgres | Bemerkung |
|---|---|---|---|---|
| **Ist** – `flake.lock`, `mayflower/nixpkgs#mf-stable` @ 2024-02-07 | 3.11.6 | **4.2.9** | 15.5 (lib) | Django 4.2 ist seit April 2026 EOL |
| `mayflower/nixpkgs#mf-stable` @ **HEAD (2026-06-03)** | 3.13.11 | **4.2.28** | – | Branch wird gepflegt, hängt aber auf nixos-25.11 |
| `NixOS/nixpkgs#nixos-25.11` | 3.13.12 | 4.2.30 | 17.10 | |
| `NixOS/nixpkgs#nixos-26.05` (aktuelles Stable) | 3.13.14 | **5.2.16** | 17.10 | |
| `NixOS/nixpkgs#nixos-unstable` | 3.14.6 | 5.2.16 | – | |

**Kernbefund:** Ein reines `nix flake update` auf `mf-stable` bringt Python 3.13, aber **weiterhin
Django 4.2** — also weiterhin EOL. Django 5.2 LTS gibt es erst ab `nixos-26.05`.

Zu klären (→ Plan F3): `mf-stable` existiert vermutlich wegen des Mayflower-Binary-Caches /
interner Backports. Optionen:
- **(a) empfohlen:** `nixpkgs`-Input auf `github:NixOS/nixpkgs/nixos-26.05` → Django 5.2.16,
  Python 3.13.14, PG 17.10 ohne Overrides.
- (b) `mf-stable` behalten und `mf-stable` intern auf 26.05 heben lassen (Mayflower-seitige Aufgabe).
- (c) `mf-stable` behalten und Django per Overlay auf 5.2 pinnen → Dauer-Wartungslast, nicht empfohlen.

**Django 5.2 LTS ist die Zielversion** (Support bis April 2028, und die Version, die nixpkgs
tatsächlich liefert — nixpkgs führt kein Django 6.x). Damit ist Plan-Frage F2 faktisch entschieden.

## 0.2 Läuft es? – ja, vollständig

- `nix develop`-Umgebung baut, `manage.py check` läuft.
- `makemigrations` + `migrate` (SQLite) → OK. `manage.py check`: 3 Warnungen, alle `models.W042`
  (fehlendes `DEFAULT_AUTO_FIELD`). `check --deploy`: 9 Issues (siehe 0.3).
- `nix build .#dockerImages.x86_64-linux.{default,nginx}` → **beide Images bauen fehlerfrei.**
  Im nginx-Image steckt nginx 1.24.0 / openssl 3.0.12 (ebenfalls alt, kommt mit dem Lock-Bump mit).
- Happy Path funktional durchgetestet (Skript: [notes/baseline_probe.py](baseline_probe.py),
  21 Fälle, läuft gegen eine temporäre Test-DB).

### Verhalten Django 4.2.9 vs. 5.2.16 – **identisch**

Das Probe-Skript wurde auf beiden Versionen gefahren. **Alle 21 Fälle verhalten sich gleich**,
inklusive Statuscodes, Redirect-Ziele, Mail-Anzahl/-Betreffs, Token-Längen und
`get_amount_used_unused()`-Tupel. Zusätzlich:

- Die von Django 4.2 erzeugte `0001_initial` **applied sauber auf 5.2**.
- `makemigrations --check --dry-run` auf 5.2 → `No changes detected`, also **kein Schema-Drift**.
- `USE_L10N` (in Django 5.0 entfernt) wird stillschweigend ignoriert, **kein Fehler**.
- `manage.py check` auf 5.2 zeigt exakt dieselben 3 `W042`-Warnungen, keine neuen Deprecations.

**Konsequenz für Phase 2:** Das Django-Upgrade selbst ist verhaltensneutral und risikoarm.
Der Aufwand steckt nicht im Upgrade, sondern in den Altlasten (Migrations, Settings, Views).

### Bestätigte Bugs (aus dem Probe-Lauf, auf beiden Django-Versionen)

| Fall | Ergebnis |
|---|---|
| `GET /vote/create` | **500** `MultiValueDictKeyError: 'title'` (B3) |
| `POST /vote/<id>/vote` ohne `token`-Feld | **500** `UnboundLocalError: token_string` (B2) |
| `POST /vote/<id>/manage` ohne `token`-Feld | **500** `MultiValueDictKeyError: 'token'` (**neu: B11**) |
| `POST /vote/create` mit ungültiger Mailadresse | **500** `ValidationError` (ungefangen, **neu: B12**) |
| `POST /vote/create` mit `type=quatsch` | **500** `Exception('Invalid poll type')` (B3) |
| `POST /vote/create` mit 3× derselben Adresse | 3 Tokens, 3 Mails → **dieselbe Person wählt 3×** (B6) |

### Verhalten, das korrekt ist und so bleiben muss (Regressionsschutz)

- Choices werden getrimmt, Leerzeilen verworfen: `"Ja\nNein\n\n  Vielleicht  \n"` → `['Ja','Nein','Vielleicht']`.
- `identifier` = 64 Zeichen, `token_string` = 128, `creator_token` = 256.
- Nach dem Abstimmen wird der Token gelöscht; beim letzten Token schließt die Umfrage automatisch
  (`is_active=False`) und `/vote/<id>/` redirected auf `/results`.
- `multiple_choice`: unvollständiger POST → Fehlermeldung, **Transaktion rollt zurück**
  (Stimmen bleiben 0, Token bleibt erhalten). Das ist korrekt und muss so bleiben.
- Vorzeitiges Schließen per `creator_token` funktioniert; die ungenutzten Tokens zählen danach
  im Ergebnis als „Abstentions" — `get_amount_used_unused()` → `(0, 2, 2)`.
- `num_tokens=None`-Pfad (Alt-Polls ohne Empfängerliste) summiert über `Choice.votes` → `(3, 1, 4)`.
- `GET /` → 302 auf `vote/`.

## 0.3 Prod-Zustand

> ### ⚠️ KORREKTUR 2026-08-03 – der Abschnitt unten beschreibt das FALSCHE Deployment
>
> Ich hatte `briefwahl.mayflower.cloud` / `k8s/settings.py` für die Produktion gehalten.
> Tatsächlich:
>
> - **Produktion ist `wahlcomputer.mayflower.de`**, konfiguriert durch ein vom NixOS-Modul
>   `mayflower.demockrazy` **generiertes** Settings-Modul `demockrazy_config`, das
>   **`DEBUG = False`** setzt. (Zwischenschritt, ebenfalls korrigiert: ich nahm zunächst an, eine
>   `local_settings.py` täte das – siehe [deployment.md](deployment.md).)
> - **Das k8s-Deployment ist abgeschaltet.** `k8s/`, `nix/*-image.nix`, `.sops.yaml` und der
>   Image-Build in der CI sind toter Code (→ Plan 5.1).
> - Der `SECRET_KEY` im weitergegebenen `local_settings.py` war vom User redigiert, **nicht** der
>   deployte Wert. Kein Problem.
>
> **Der unten beschriebene Mailadressen-Leak über die 500-Pfade ist damit nicht
> produktionsrelevant.** Die 500-Pfade selbst (B2/B3/B11/B12) bleiben Bugs und werden in Phase 3
> gefixt – aber ohne Debug-Seiten sind sie hässlich, nicht gefährlich. Kein Hotfix nötig.
>
> Zwei neue Befunde aus dem echten Prod-Setup: **SQLite in Produktion** (B13, `DATABASES` wird nicht
> überschrieben, in Kombination mit `ATOMIC_REQUESTS=True` Lock-Risiko) und **fehlende
> Secure-Cookie-/HSTS-Flags** (B14).
>
> Der Abschnitt bleibt als Analyse stehen: er dokumentiert, was ein Django-Deployment mit
> `DEBUG=True` preisgibt – relevant, falls das k8s-Setup je wiederbelebt wird, und als Begründung
> für die sicheren Defaults in Phase 2.4.

### `DEBUG=True` – galt für das inzwischen abgeschaltete k8s-Deployment (ursprüngliche Analyse)

Das damalige `k8s/settings.py` importierte `from demockrazy.settings import *` und überschrieb
`DEBUG` **nicht**. Effektive Prod-Settings, ausgewertet mit gesetzten Env-Variablen:

```
DEBUG                    = True      <-- !!
ALLOWED_HOSTS            = ['briefwahl.mayflower.cloud']
VOTE_SEND_MAILS          = True
SECURE_SSL_REDIRECT      = False
SESSION_COOKIE_SECURE    = False
CSRF_COOKIE_SECURE       = False
SECURE_HSTS_SECONDS      = 0
CSRF_TRUSTED_ORIGINS     = []
```

Das ist in Kombination mit den 500-Pfaden oben relevant: **jeder im Internet kann durch einen
trivialen Request eine Django-Debug-Fehlerseite auslösen.** Gemessen wurde, was so eine Seite
tatsächlich preisgibt (Skript im Scratchpad, Prod-Settings lokal simuliert):

| | |
|---|---|
| **Nicht** geleakt | `SECRET_KEY`, DB-Passwort, SMTP-Passwort – Django *cleanst* diese Settings zuverlässig |
| Geleakt | DB-Benutzername, SMTP-Host, absolute Dateipfade, Quellcode-Auszüge, kompletter übriger Settings-Dump, POST-Daten des Requests |
| **Kritisch geleakt** | **Die eingegebenen Wähler-Mailadressen.** Über `POST /vote/create` mit einer absichtlich kaputten Adresse in der Liste erscheinen die *gültigen* Adressen der Liste in den Frame-Locals der Fehlerseite. Ebenso bei `type=quatsch`. |

Abstimmungs-Tokens tauchen auf diesen Pfaden **nicht** auf (kein 128-Zeichen-Match im Response-Body) —
die Anonymität der Stimmen ist dadurch also nicht direkt gebrochen. Es ist eine
Informationspreisgabe personenbezogener Daten (Mailadressenlisten) plus Infrastrukturdetails.

→ **`DEBUG=False` ist der erste Fix, unabhängig vom Rest des Plans.** Ein Einzeiler in
`k8s/settings.py`, sofort deploybar, ohne auf Phase 1/2 zu warten.
Empfehlung: als eigener Hotfix-Commit vorziehen. Danach die 500-Pfade in Phase 3 richtig fixen.

### Noch offen (braucht Server-Zugang – kann ich nicht selbst)

**Prod-Schema-Stand** (Plan-Frage F12), Gegenprobe zu [notes/baseline-schema.sql](baseline-schema.sql),
bevor die eingecheckte `0001_initial` in Phase 2.1 scharf gestellt wird. Prod ist SQLite, also
nur lesend auf dem Server:

```bash
nix run nixpkgs#sqlite -- -readonly db.sqlite3 ".schema vote_poll" ".schema vote_choice" ".schema vote_token" \
  "SELECT app, name, applied FROM django_migrations WHERE app='vote';"
```

Daraus ergibt sich der Deploy-Pfad:
- Eintrag `vote/0001_initial` vorhanden **und** Schema passt → `migrate` tut nichts, alles gut.
- Kein Eintrag → `migrate` würde `CREATE TABLE` auf existierende Tabellen fahren ⇒ `--fake-initial`.
- Anders benannter oder zusätzlicher Eintrag → einzeln bewerten, bevor irgendwas läuft.

**Deployment-Mechanik** (Plan-Frage F11): wie `wahlcomputer.mayflower.de` gestartet wird, wo die
`db.sqlite3` liegt und ob sie gesichert wird. Blockiert Phase 5.2/5.4 und damit die Frage, ob das
Django-Upgrade dort überhaupt ankommt.

## 0.4 Schema-Snapshot

Abgelegt: [notes/baseline-schema.sql](baseline-schema.sql) – die drei `vote_*`-Tabellen
inkl. der beiden FK-Indizes, erzeugt aus `makemigrations` auf Django 4.2.9.
Referenz für die Verifikation der eingecheckten Migration (Plan 2.1).

Auffällig fürs Datenmodell (→ Plan 3.6): **kein** `UNIQUE` auf `vote_token.token_string`
und **kein** `UNIQUE`/Index auf `vote_poll.identifier`, obwohl beide als eindeutig behandelt
und `identifier` als Lookup-Key in jedem Request benutzt wird.

---

## Fazit / Empfehlung für die Reihenfolge

*(aktualisiert nach der Deployment-Klärung)*

1. **Kein Hotfix nötig** – Prod läuft mit `DEBUG=False`.
2. Phase 1 (Tooling + Tests) als Nächstes; das Probe-Skript wird zur Testbasis (Plan 1.4).
   Nichts davon ist blockiert, `nixpkgs`-Entscheidung (F3) ist gefallen.
3. Phase 2 ist risikoärmer als angenommen: Django 4.2 → 5.2 ist verhaltensneutral. Der Blocker
   bleibt B1, und 2.1 braucht den Prod-Schema-Stand (F12).
4. Phase 5 hat sich von „k8s modernisieren" zu „k8s entfernen" gedreht und ist damit deutlich
   kleiner – dafür ist **F11 (wie wird eigentlich deployt?) jetzt der wichtigste offene Punkt**:
   ohne die Antwort weiß ich nicht, ob das Upgrade in Produktion ankommt.
