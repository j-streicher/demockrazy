# Zu prüfen / zu erledigen außerhalb dieses Repos

> **Wozu diese Datei.** Alles hier liegt **nicht in diesem Repo** – im Deployment-Repo (Colmena,
> NixOS-Modul, Proxy-vhost), auf der Prod-Node, oder es ist eine Frage an den User. Ich mache davon
> nichts selbst (Arbeitsregel 7: kein Rollout) und ich schaue auch nicht danach
> (Arbeitsregel 10: im Workspace bleiben). Was ich brauche, steht hier mit Befehl und Begründung.
>
> Angelegt 2026-08-04. Detailanalysen: [deployment.md](deployment.md) und [plan.md](plan.md).

---

## A. Blockiert mich – eine Antwort genügt

### A1. `VOTE_MAIL*`-Settings im Modul? (F17) — **vor dem Deploy**

Bis 3.4 standen die Mail-Texte als Strings in `settings.py`. Jetzt kommen sie aus Templates
(`vote/templates/vote/mail/`). **Setzt das Modul einen der vier alten Werte, wird er nach dem Deploy
stillschweigend ignoriert** – kein Fehler, keine Warnung, nur plötzlich anderer Text in den Mails.

```bash
grep -rn 'VOTE_MAIL\|VOTE_ADMIN_MAIL' .
```

- **Kein Treffer** → erledigt, nichts zu tun.
- **Treffer** → sag mir den Wortlaut, dann gehört er ins Template statt in die Settings.

`VOTE_MAIL_FROM`, `VOTE_BASE_URL` und `VOTE_SEND_MAILS` sind **absichtlich geblieben** und dürfen
weiter gesetzt werden.

### A2. Kommt `X-Forwarded-Proto` bei Django an? (F15) — blockiert 2.7

Gebraucht wird zweierlei vom **Proxy-Host** (nicht von der Node):

```bash
# 1. Ist recommendedProxySettings an? Das setzt X-Forwarded-Proto $scheme.
grep -rn 'recommendedProxySettings' .
# 2. Der vollstaendige proxyPass-Wert des vhosts (war abgeschnitten)
grep -rn -A3 'wahlcomputer.mayflower.de' .
```

**Warum das zählt:** ohne den Header hält Django den Request für `http`. Djangos CSRF-Prüfung
vergleicht seit 4.0 den `Origin`-Header gegen Schema + Host – also `http://…` gegen das
`https://…`, das der Browser schickt. Das müsste **jede Stimmabgabe mit 403** abweisen. Sie tut es
offenbar nicht, also liefert *irgendwas* das Schema. Ich will wissen was, bevor an TLS- oder
CSRF-Settings etwas geändert wird.

Falls es der Header ist und das Modul `SECURE_PROXY_SSL_HEADER` **nicht** setzt: dann ist das die
eine Zeile, die dort noch fehlt.

### A3. Wie hoch ist das Rate-Limit von `smtp.mayflower.de`? (F20) — blockiert Ziel 2

Eingegrenzt ist es schon: **30 Mails gingen immer durch, bei 50 kam `450 4.7.1 Error: too much mail
from …`.** Die Grenze liegt also zwischen 30 und 50 pro Zeitfenster. Für eine belastbare Taktung
fehlen drei Angaben:

```bash
postconf | grep -i 'rate_limit\|anvil'      # auf dem Mailserver
```

- der Wert von `smtpd_client_message_rate_limit` (oder was eine Policy dort setzt),
- die Fensterlänge `anvil_rate_time_unit` (Default 60 s),
- **die vollständige Fehlerzeile** – der abgeschnittene Teil hinter *from* sagt, ob auf Client-IP
  oder auf Absenderadresse gezählt wird. Davon hängt ab, ob Taktung überhaupt hilft oder ob eine
  zweite Absenderadresse Teil der Lösung ist.

Ohne diese Zahlen wäre jede Batch-Größe und jede Pause geraten.

---

## B. Am vorgelagerten Proxy – Härtung, unabhängig vom Deploy

Beides betrifft den vhost `wahlcomputer.mayflower.de` im Deployment-Repo. Beides ist **unabhängig**
davon, ob der neue Stand ausgerollt wird – außer beim CSP, siehe die Einschränkung dort.

### B1. CSP-Snippet einbinden

`config.mayflower.snippets.nginxCSPSnippet` **existiert, ist auf diesem vhost aber nicht
eingebunden** – dort stehen nur HSTS, FrameOpts und GeneralProtect.

**Das ging vorher nicht sinnvoll und geht jetzt:** bis 4.1/4.3 lagen Bootstrap 3, jQuery und
Highcharts vendored *und* es gab im Markup Reste, die auf Fremd-Hosts zeigten. Inzwischen ist alles
selbst gehostet, es gibt **keinen einzigen externen Host** mehr im Dokument – kein CDN, keine
Web-Fonts, keine externen Bilder. Das ist die Voraussetzung, an der ein `default-src 'none'` sonst
scheitert.

⚠️ **Erst nach dem Deploy einschalten**, nicht davor. Der heute laufende Stand (`master`, `rev
3074dbb`) lädt noch Bootstrap 3 und Highcharts und hat im `base.html` einen auskommentierten
`googleapis.com`-Block; ob der aktuelle Produktionsstand unter dem CSP läuft, habe ich **nicht**
geprüft und kann es nicht – der Snippet liegt im Deployment-Repo.

**Was ich geprüft habe, ist der neue Stand gegen die Direktiven, die du mir gezeigt hast** – gelesen,
nicht ausprobiert, also bitte gegenprüfen:

| Was die Seite braucht | Direktive im Snippet | passt? |
|---|---|---|
| Inline-`<script>` auf der Ergebnisseite (Chart-Init) | `script-src 'unsafe-inline'` | ✅ |
| `{{ …|json_script }}`-Datenblock | dito (wird nicht ausgeführt) | ✅ |
| Ein Inline-`style`-Attribut in `results.html` | `style-src 'unsafe-inline'` (greift über `style-src-attr`) | ✅ |
| Bootstraps `data:`-Bilder (Navbar-Toggler, Select-Pfeil) | `img-src 'self' data:` | ✅ |
| Bootstrap-JS, Chart.js, CSS – alle aus `/static/` | `script-src 'self'`, `style-src 'self'` | ✅ |
| kein `fetch`/XHR, keine Web-Fonts, keine iframes | `connect-src`/`font-src`/`frame-src` ungenutzt | ✅ |

**Vorgehen, das ohne Risiko ist:** zuerst als `Content-Security-Policy-Report-Only` einbinden. Dann
protokolliert der Browser Verstöße in der Konsole, ohne etwas zu blocken. Sechs Seiten ansehen —
`/vote/`, `/vote/<id>/`, `/vote/<id>/vote`, `/vote/<id>/success`, `/vote/<id>/manage`,
`/vote/<id>/results` — und wenn die Konsole leer bleibt, auf den scharfen Header umstellen.

**Zwei Ergänzungen, die sich beim Lesen anbieten** (deine Entscheidung, nicht nötig):

- `form-action 'self'` – fehlt im Snippet und fällt **nicht** auf `default-src` zurück, Formulare
  funktionieren also so oder so. Mit der Direktive könnte ein gefundener Injection-Punkt das
  Formular nicht auf einen fremden Host umbiegen.
- `frame-ancestors 'none'` – siehe B2, das löst dort das Problem gleich mit.

### B2. `X-Frame-Options` ist heute widersprüchlich

Der Proxy setzt `sameorigin`, **Djangos `XFrameOptionsMiddleware` setzt per Default `DENY`** – es
gehen **beide Header raus**. Bei widersprüchlichen Werten ist das Browserverhalten nicht
festgelegt; im schlechtesten Fall wird der Header ignoriert, also **schwächer als jede der beiden
Absichten**. Das ist heute schon so, unabhängig von meinen Änderungen.

Eine Seite sollte ihn besitzen. Drei Wege, in der Reihenfolge, die ich vorziehen würde:

1. **`frame-ancestors 'none'` in den CSP** und das `FrameOpts`-Snippet für diesen vhost weglassen.
   `frame-ancestors` ist der moderne Ersatz und **hat in Browsern, die beides kennen, Vorrang vor
   `X-Frame-Options`** – damit ist der Widerspruch strukturell weg statt nur weggeräumt.
2. `FrameOpts`-Snippet für diesen vhost weglassen, Djangos `DENY` gewinnen lassen. Die App soll
   nirgends eingebettet werden, `DENY` ist das strengere und der Default ist richtig.
3. Im Modul `X_FRAME_OPTIONS = "SAMEORIGIN"` setzen, damit beide dasselbe sagen. Funktioniert, lässt
   aber den doppelten Header stehen.

---

## C. Am NixOS-Modul / Colmena – sonst erreicht der neue Stand Prod nicht

### C1. `rev` + `sha256` bumpen

Das Modul pinnt `rev = 3074dbb` per `fetchFromGitHub` – **das ist der Basis-Commit dieses Branches.**
Ohne Bump ändert sich in Produktion **nichts**. Beim Bump `version = "2024-02-08"` im Derivation
gleich mitziehen (nur Metadatum).

### C2. Colmena-Flake auf `mf-next`

Die Django-Version kommt aus der nixpkgs, die den Host auswertet, **nicht** aus `pyproject.toml`:
`mf-stable` → Django 4.2.28 (**EOL**), `mf-next` → 5.2.15. `pyproject.toml` dokumentiert die
Anforderung, erzwingt sie nicht.

### C3. Die SQLite-`OPTIONS` ins Modul übernehmen (5.4)

**Das ist die wichtigste Zeile in dieser Datei**, weil sie sonst still verloren geht. Das generierte
`demockrazy_config` setzt `DATABASES` **komplett neu** – genau der Mechanismus, über den
`ATOMIC_REQUESTS` zehn Jahre wirkungslos war (B16). Die Optionen, die ich in `settings.py` gesetzt
habe, kommen damit in Produktion **nicht** an.

Gebraucht wird in `DATABASES['default']`:

```python
"OPTIONS": {
    "transaction_mode": "IMMEDIATE",
    "init_command": "PRAGMA journal_mode=WAL;",
    "timeout": 20,
}
```

**Warum es sich lohnt, gemessen:** 8 gleichzeitige Lese-dann-Schreib-Transaktionen × 25 Runden –
mit Djangos Defaults **36 von 200 erfolgreich, 164 × `database is locked`**; mit diesen Optionen
**200 von 200**, für 0,13 s mehr Laufzeit. Der Grund ist `transaction_mode`: bei Djangos `DEFERRED`
muss eine Transaktion, die erst liest und dann schreibt – die Form von `vote()` – ihre Sperre
hochstufen, und das kann SQLite **nicht warten lassen**, es kommt sofort `SQLITE_BUSY` ohne
Rücksicht auf `timeout`.

Über die `djangoSettings`-Option des Moduls **ohne Modul-Änderung testbar**.

### C4. `ALLOWED_HOSTS` für die `/healthz`-Probe

`GET /healthz` gibt `200 ok`, wenn der Prozess Requests bedienen und die Datenbank lesen kann, sonst
`503 database unavailable`. `ALLOWED_HOSTS` ist in Prod `["wahlcomputer.mayflower.de"]` – **eine
Monitoring-Probe gegen `localhost` bekommt einen 400 und sieht wie ein Ausfall aus.** Also entweder
mit passendem `Host`-Header proben oder `ALLOWED_HOSTS` erweitern.

---

## D. Beim Deploy und danach

### D1. `migrate` ist kein No-Op mehr

`0001`/`0002` sind namensgleich zu den zwei Prod-Migrations von 2016 und werden übersprungen.
**`0003` wird angewendet und schreibt `vote_poll` und `vote_token` neu** – so hängt SQLite einen
Constraint an. Gegen ein Prod-Abbild geprüft: Daten unversehrt, FKs konsistent, Spaltenreihenfolge
unverändert ([phase-2-migrations.md](phase-2-migrations.md)). `migrate` läuft im `preStart` vor dem
Dienststart, es gibt also keine parallelen Schreiber, und borg-Backup liegt vor (03:00/04:00).

### D2. Direkt nach dem Deploy: den Check gegen die echten Settings fahren

```bash
DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check
```

Meldet `demockrazy.W001`, falls C3 vergessen wurde. Genau dafür gibt es den Check – damit dieser
Fehler nicht wieder zehn Jahre still bleibt.

### D3. Was der Ersteller nach dem Deploy **nicht** mehr sieht

Heute zeigt `create.html` eine Liste der Zustellfehler – daraus kam die `450`-Meldung, mit der das
Mailproblem diagnostiziert wurde. **3.4 hat diese Liste entfernt**, bewusst: der Versand läuft jetzt
nach dem Commit der Transaktion, die Seite ist dann schon gerendert. Die Fehler gehen ins Log:

```bash
journalctl -u demockrazy --since '-1h' | grep -i 'Zustellung\|SMTP'
```

Das ist der stärkste Grund für einen echten Zustellbericht in Ziel 2 – und der ist mit F8 („lieber
anonymer") bewusst eng gefasst, siehe [plan.md](plan.md) §11.4.

### D4. Mail-Wortlaut einmal gegenlesen

Der Wortlaut ist byteweise erhalten und per Test festgenagelt, **inklusive** führender und
abschließender Leerzeile und des überzähligen `"` nach „Deutsche Bahn". Falls A1 einen Treffer
hatte, ist das die Stelle, an der es auffällt.
