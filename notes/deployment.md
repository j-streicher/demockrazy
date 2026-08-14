# Deployment: `mayflower.demockrazy` – Analyse

Grundlage: das NixOS-Modul des Users (2026-08-03) + die Colmena-Node-Config für
`wahlcomputer.mayflower.de`. **Das Modul liegt nicht in diesem Repo** – Änderungen daran sind
Sache des Users.

## Wie es läuft

```
colmena → nodes/wahlcomputer.nix → mayflower.demockrazy.enable = true
   → systemd.services.demockrazy
        preStart:  manage.py migrate && manage.py collectstatic --noinput
        ExecStart: uwsgi --json … (4 Prozesse, Socket /run/demockrazy/uwsgi.socket)
   → nginx: uwsgi_pass unix:/run/demockrazy/uwsgi.socket, /static aus /var/lib/demockrazy/
```

- `DJANGO_SETTINGS_MODULE=demockrazy_config` – ein **im Modul generiertes** Python-Paket, das
  `from demockrazy.settings import *` macht und danach überschreibt.
- Code läuft aus dem Nix-Store (`${pkg}/share/demockrazy`), `ProtectSystem = "full"`,
  `ReadWritePaths = /run/demockrazy /var/lib/demockrazy`.
- Deshalb sind DB und Static **absolut** außerhalb des Stores gesetzt:
  `NAME = '/var/lib/demockrazy/db.sqlite3'`, `STATIC_ROOT = '/var/lib/demockrazy/static'`.
  **Korrektur zu einer früheren Annahme:** `BASE_DIR` ist *nicht* `/var/lib/demockrazy`, sondern der
  Store-Pfad. Die beiden Verzeichnisse hängen nur an diesen expliziten Overrides.

## ⚠️ Wie mein Upgrade nach Produktion kommt (und warum es das aktuell nicht tut)

Das Modul zieht die App **von GitHub an einem gepinnten Commit**:

```nix
src = pkgs.fetchFromGitHub {
  owner = "mayflower"; repo = "demockrazy";
  rev = "3074dbb79c882ec999028dd2ef1b447cd0638ddc";   # ← genau der Basis-Commit dieses Branches
  sha256 = "sha256-4MJkKwFGhOGMJ1jphtgM1H94oOdZo3ta0ucCZe/cOUs=";
};
```

**Zwei Änderungen sind nötig, beide im Repo des Users, nicht hier:**

1. **`rev` + `sha256`** auf den gemergten Stand dieses Branches heben. Ohne das ändert sich in
   Produktion gar nichts, egal was hier passiert.
2. **Die Django-Version kommt aus der nixpkgs des Colmena-Flakes, nicht aus diesem Repo.**
   Das Modul baut `djangoenv` aus `pkgs.python3Packages.django` – also der nixpkgs, mit der der
   *Host* evaluiert wird. Gemessen:
   - `mf-stable` → Django **4.2.28** (EOL)
   - `mf-next` → Django **5.2.15**

   Solange das Colmena-Flake auf `mf-stable` steht, läuft Produktion weiter auf Django 4.2,
   auch nach einem `rev`-Bump. `pyproject.toml` in diesem Repo hat darauf **keinen Einfluss** –
   es dokumentiert die Anforderung, erzwingt sie aber nicht.

   Phase 0 hat verifiziert, dass der Code auf 4.2.9 **und** 5.2.16 identisch läuft, d. h. die
   Reihenfolge ist frei: `rev`-Bump und nixpkgs-Wechsel können unabhängig erfolgen.

## Was das für den Löschcommit `90ab23b` bedeutet

**Kein Risiko – bestätigt.** Das Modul konsumiert *keine* Flake-Outputs dieses Repos: es baut
seinen eigenen uwsgi (`pkgs.uwsgi.override`), seinen eigenen `configModule` und benutzt vom Repo
nur den **Quelltext** (`cp -R .`). Die gelöschten `packages.uwsgi` / `packages.django_config` /
`dockerImages` waren tatsächlich nur für das abgeschaltete k8s-Setup da.

## Was die Prod-Settings tatsächlich setzen

| Setting | Wert | Bemerkung |
|---|---|---|
| `DEBUG` | **`False`** | **F14 beantwortet.** Kein Leak-Risiko, kein Hotfix nötig. |
| `SECRET_KEY` | aus `secretKeyFile` (sops) | zur Laufzeit gelesen |
| `DATABASES` | SQLite, `/var/lib/demockrazy/db.sqlite3` | B13 bleibt bestehen |
| `STATIC_ROOT` | `/var/lib/demockrazy/static` | von nginx serviert |
| `CSRF_COOKIE_SECURE` | `True` | `secureCookies` default |
| `SESSION_COOKIE_SECURE` | `True` | dito |
| `LOGGING` | Console-Handler, Level `INFO` | |
| `EMAIL_*` | `smtp.mayflower.de:587`, STARTTLS, User + sops-Passwort | |
| `VOTE_SEND_MAILS` | `True` | |
| `ALLOWED_HOSTS` | `["wahlcomputer.mayflower.de"]` | |

⇒ **B14 war zu pauschal:** die beiden Cookie-Flags *sind* gesetzt. Es fehlen weiterhin
`SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` und `CSRF_TRUSTED_ORIGINS` – dazu unten.

⚠️ **Offen für den Deploy (F17):** in dieser Tabelle steht **kein** `VOTE_MAIL_SUBJECT`,
`VOTE_MAIL_TEXT`, `VOTE_ADMIN_MAIL_SUBJECT` oder `VOTE_ADMIN_MAIL_TEXT` – Schritt 3.4 hat diese vier
aus `settings.py` entfernt, der Wortlaut kommt jetzt aus Templates in
`vote/templates/vote/mail/`. Sollte das Modul (oder seine `djangoSettings`-Option) doch einen davon
setzen, wird der Wert nach dem Deploy **stillschweigend ignoriert** und Produktion verschickt den
Repo-Wortlaut. Im Colmena-Repo zu prüfen:
`grep -rn 'VOTE_MAIL\|VOTE_ADMIN_MAIL'`. `VOTE_BASE_URL`, `VOTE_MAIL_FROM` und `VOTE_SEND_MAILS`
sind **absichtlich geblieben** und weiter überschreibbar.

`local_settings.py` ist **nirgends im Spiel**: `demockrazy_config` ersetzt diesen Mechanismus.
Der `try/except` am Ende von [demockrazy/settings.py](../demockrazy/settings.py) greift trotzdem, weil
`demockrazy_config` die Datei importiert – und schreibt bei **jedem Start**
`No local settings found..` ins Syslog. Kleines, echtes Ärgernis für 2.4.

## Fallen für Phase 2.4 / 2.7 – hier hätte ich Prod kaputtgemacht

1. **`SECRET_KEY` darf beim Import von `demockrazy.settings` nicht hart fehlschlagen.**
   `demockrazy_config` setzt den Key **nach** dem `import *`. Ein
   `SECRET_KEY = os.environ["…"]` oder ein `raise ImproperlyConfigured` in `settings.py` würde
   Produktion beim Start sofort töten. Also: leerer/`None`-Default, kein Raise.
   Django meckert erst beim *Zugriff* auf einen leeren Key – und bis dahin hat
   `demockrazy_config` ihn gesetzt.

2. **`SECURE_SSL_REDIRECT` / HSTS nicht einfach anschalten.**
   Die Node öffnet nur Port **80** (`firewall.allowedTCPPorts = [ 80 ]`), der vhost hat kein
   `forceSSL`/`enableACME`. TLS wird also **vorgelagert** terminiert. Ohne
   `SECURE_PROXY_SSL_HEADER` sieht Django `http` ⇒ `SECURE_SSL_REDIRECT = True` erzeugt eine
   **Redirect-Schleife**. Diese Settings gehören ins Modul, zusammen mit dem Proxy-Header –
   nicht als Default hierher.

3. **Offene Frage `CSRF_TRUSTED_ORIGINS` (→ F15).** Seit Django 4.0 prüft der CSRF-Schutz den
   `Origin`-Header strikt gegen das aus `request.is_secure()` abgeleitete Schema. Ohne
   `SECURE_PROXY_SSL_HEADER` wäre das `http://…`, der Browser sendet aber `https://…`.
   Nach Aktenlage müssten POSTs (also *jede Stimmabgabe*) mit 403 scheitern – tun sie offenbar
   nicht, also liefert irgendwas das Schema oder den Header. **Das will ich verstanden haben, bevor
   ich in 2.7 an CSRF-/TLS-Settings gehe.** Konkret zu klären: setzt der vorgelagerte Proxy
   `X-Forwarded-Proto`, und gibt es ein Mayflower-Default für `SECURE_PROXY_SSL_HEADER`?

## Nebenbefunde

- `preStart` ruft **`migrate`**, nicht `makemigrations` – gut. Am gepinnten Commit ist das für
  `vote` ein No-Op, weil dort gar keine Migrationsdateien existieren (Django überspringt Apps ohne
  Migrations). **Nach dem `rev`-Bump ist es kein No-Op mehr** *(korrigiert 2026-08-03, nach 3.6)*:
  `0001`/`0002` werden übersprungen, weil ihre Namen schon in `django_migrations` stehen, aber
  **`0003_model_constraints_and_choices` wird angewendet und schreibt `vote_poll` und `vote_token`
  neu** – so hängt SQLite einen `UniqueConstraint` an eine bestehende Tabelle.
  Gegen ein Abbild des Prod-Schemas geprüft: Daten unversehrt, `PRAGMA foreign_key_check` leer,
  Spaltenreihenfolge unverändert; Duplikate gibt es keine (auf Prod nachgesehen). Details in
  [notes/phase-2-migrations.md](phase-2-migrations.md).
  **Dass `migrate` im `preStart` läuft, ist dabei der entscheidende Umstand:** der Dienst ist zu
  diesem Zeitpunkt noch nicht gestartet, es gibt also keine parallelen Schreiber auf der Datei.
- `collectstatic --noinput` läuft bei jedem Start ⇒ die Umstellung auf
  `ManifestStaticFilesStorage` (4.4) ist gefahrlos möglich.
- `version = "2024-02-08"` im Derivation ist nur Metadatum, aber beim `rev`-Bump gleich mitziehen.
- `processes = 4` bei SQLite: vier uwsgi-Worker auf einer SQLite-Datei ⇒ genau das Szenario aus
  B13. `timeout`/WAL in den `DATABASES['default']['OPTIONS']` wären eine kleine, wirksame
  Härtung – gehört ins Modul oder über die `djangoSettings`-Option.
- Die `djangoSettings`-Option (verbatim Settings) ist ein guter Hebel: damit lässt sich Neues in
  Produktion testen, ohne das Modul zu ändern.

## Der vorgelagerte Proxy – vom User geliefert 2026-08-04 (zu F15)

Die TLS-Terminierung liegt **nicht** auf der Node, sondern auf einem vorgeschalteten nginx. Dessen
vhost:

```nix
"wahlcomputer.mayflower.de" = {
  forceSSL = true;
  enableACME = true;
  extraConfig =
    config.mayflower.snippets.nginxHSTSSnippet
    + config.mayflower.snippets.nginxFrameOptsSnippet
    + config.mayflower.snippets.nginxGeneralProtectSnippet;
  locations."/".proxyPass = "http://wahlcomputer.…";
};
```

Die Snippets setzen:

| Snippet | Header |
|---|---|
| `nginxHSTSSnippet` | `Strict-Transport-Security: max-age=31536000;` (1 Jahr, ohne `includeSubDomains`/`preload`) |
| `nginxFrameOptsSnippet` | `X-Frame-Options: sameorigin` |
| `nginxGeneralProtectSnippet` | `X-XSS-Protection: 1; mode=block`, `Referrer-Policy: same-origin, strict-origin-when-cross-origin`, `X-Content-Type-Options: nosniff` |
| `nginxCSPSnippet` | existiert, ist auf diesem vhost aber **nicht** eingebunden |

**Das dreht 2.7 um.** Von den vier offenen Settings sind zwei gegenstandslos und eines gefährlich:

- **`SECURE_SSL_REDIRECT` – nicht setzen, unnötig.** `forceSSL = true` macht die
  HTTP→HTTPS-Umleitung bereits einen Hop weiter oben. In Django wäre sie doppelt und ohne
  `SECURE_PROXY_SSL_HEADER` eine Redirect-Schleife.
- **`SECURE_HSTS_SECONDS` – nicht setzen, sonst doppelter Header.** HSTS steht schon, mit einem Jahr.
  Zwei `Strict-Transport-Security`-Header sind undefiniertes Verhalten, kein zusätzlicher Schutz.
- **Neuer Nebenbefund: `X-Frame-Options` ist heute widersprüchlich.** Der Proxy sagt `sameorigin`,
  Djangos `XFrameOptionsMiddleware` sagt per Default `DENY` – **beide Header gehen raus**. Bei
  widersprüchlichen Werten ist das Browserverhalten nicht festgelegt; im schlechtesten Fall wird der
  Header ignoriert, also *schwächer* als jede der beiden Absichten. Eine Seite sollte ihn besitzen.
  Da die App nicht eingebettet werden soll, ist `DENY` das strengere und Djangos Default richtig –
  dann gehört das `FrameOpts`-Snippet für diesen vhost weg. Umgekehrt geht auch, aber nicht beides.
- **Offen bleibt allein die Kernfrage von F15:** kommt `X-Forwarded-Proto` bei Django an? Das hängt
  an `services.nginx.recommendedProxySettings` auf dem Proxy-Host; der `proxyPass`-Wert war
  abgeschnitten. **Warum das zählt:** ohne diesen Header hält Django den Request für `http`, und
  Djangos CSRF-Prüfung vergleicht seit 4.0 den `Origin`-Header gegen `http://…` statt `https://…` →
  **403 auf jede Stimmabgabe**. Das passiert offenbar nicht, also liefert *irgendwas* das Schema –
  entweder der Header, oder ein gesetztes `CSRF_TRUSTED_ORIGINS`. Das will ich gesehen haben, bevor
  hier etwas geändert wird.
- **Neue Option, die es vorher nicht gab:** der `nginxCSPSnippet` ließe sich jetzt einbinden. Sein
  `default-src 'none'; script-src 'unsafe-inline' 'self'; style-src 'self' 'unsafe-inline'` passt zum
  Bestand **seit alles vendored ist** (4.1/4.3) – kein CDN, keine Fremd-Hosts, und das inline-Script
  auf der Ergebnisseite ist durch `'unsafe-inline'` gedeckt. Das wäre der wirksamste verbleibende
  Härtungsschritt, und er gehört in den Proxy, nicht in Django.
