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

### ~~A4. Gibt es in Produktion ein Django-Staff-Konto?~~ → **ja** (2026-08-04) — Befund R2-1

`django.contrib.admin` ist installiert, `/admin/` ist geroutet, und `vote/admin.py` registrierte
`Poll`, `Choice` und `Token` ohne jede Einschränkung. Gemessen: ein angemeldeter Staff-Account sah
`creator_token` und `identifier` im Poll-Formular, konnte jeden `token_string` lesen und
**`Choice.votes` direkt setzen** -- der einzige Weg im ganzen System, der Stimmzahlen unmittelbar
verändert.

**Antwort des Users (2026-08-04): ja, es gibt ein Konto.** Damit ist R2-1 von „hoch?" zu **hoch**
geworden, und die Django-Hälfte ist erledigt (`vote/admin.py`, Commit mit R2-1 im Betreff):

- `Choice.votes` ist **nicht mehr editierbar** -- gemessen: ein POST mit `votes=9999` ändert nichts,
  und ein neu angelegter Choice startet bei 0.
- `token_string` steht **weder in der Liste noch im Formular**, ein Staff-Konto kann also keinen
  Wähler-Token mehr lesen und damit nicht abstimmen.
- `creator_token` ist aus dem Poll-Formular entfernt, `identifier` ist `readonly` (Links bleiben
  gültig).
- **Was bewusst bleibt:** Löschen und `is_active` schalten. Beides ist legitime Aufräumarbeit, und
  `LogEntry` hält fest, wer es getan hat.

**Offen und deine Seite -- der Rest lässt sich in Django nicht lösen:**

`/admin/login/` antwortet ohne jede Drosselung von Fehlversuchen (gemessen: 200, kein Rate-Limit).
Ein Deckel dagegen bräuchte eine zusätzliche Abhängigkeit; am Proxy ist es ein Zweizeiler. Sinnvoll
wäre, `/admin/` dort ganz auf ein Netz oder eine Basic-Auth zu beschränken:

```nginx
location /admin/ { allow 10.0.0.0/8; deny all; ... }
```

Und falls das Konto **niemand** benutzt: dann ist die sauberste Lösung weiter, `django.contrib.admin`
samt Route zu entfernen. Sag Bescheid, das ist ein kleiner Commit.

### A5. Ist das SMTP-Kennwort von 2023 noch gültig? — aus dem Review, Befund R8-1

`k8s/environments/default/secrets.sops.yaml` ist mit `4e15012` gelöscht, steht aber weiter in der
History (`git show master:k8s/environments/default/secrets.sops.yaml`) und enthält verschlüsselt
`secret_key`, `email_host`, `email_from` und **`email_password`**, angelegt am 2023-01-17, lesbar für
einen age- und drei PGP-Empfänger. Verschlüsselt ist das keine Preisgabe -- die Frage ist, ob das
Kennwort noch ein gültiger Zugang auf `smtp.mayflower.de` ist, denselben Mailserver, über den
Produktion heute verschickt.

**Stand 2026-08-04: du prüfst das vor dem Deploy.** Damit bleibt es hier als Punkt stehen, mit
derselben Empfehlung:

- **Account existiert nicht mehr / Kennwort rotiert** → erledigt.
- **Noch gültig** → rotieren. History umschreiben wäre unverhältnismäßig; die Rotation ist die
  Antwort.

Gehört sinnvoll neben C1--C3 in denselben Vorbereitungsschritt: du bist dann ohnehin am
Deployment-Repo.

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

**Nachtrag, gemessen bei 3.9:** der Widerspruch ist nicht der einzige doppelte Header. Django
schickt von sich aus **drei** von denen, die das `GeneralProtect`-Snippet auch setzt:

| Header | Django schickt | Snippet schickt |
|---|---|---|
| `X-Frame-Options` | `DENY` | `sameorigin` ← **Widerspruch, siehe oben** |
| `X-Content-Type-Options` | `nosniff` | `nosniff` (identisch, harmlos) |
| `Referrer-Policy` | `same-origin` | `same-origin, strict-origin-when-cross-origin` |
| `X-XSS-Protection` | – | `1; mode=block` (von allen Browsern entfernt, wirkungslos) |

Beim `Referrer-Policy` ist der Effekt gutartig: der Browser nimmt aus der zusammengesetzten Liste
den **letzten gültigen** Wert, also `strict-origin-when-cross-origin`. Für gleichherkünftige
Anfragen senden beide Werte ohnehin die vollständige URL. **Kein Handlungsdruck** – aber das Snippet
trägt für diesen vhost außer dem Widerspruch nichts bei, was Django nicht schon täte.

### B3. Access-Log: `log_format` ohne `$args` — der Rest von B9

**Das ist der einzige Punkt in dieser Datei, der aus meiner Arbeit an 3.9 folgt.** Mit 3.9 zieht der
Wähler-Token beim ersten Aufruf aus dem Query-String in ein Cookie um. Was dadurch **nicht**
verschwindet, ist die Logzeile dieses *einen* Aufrufs: der Link in der Mail trägt den Token, und
nginx protokolliert die Anfragezeile, bevor Django etwas davon sieht.

Gemessen am Dev-Server, zwei Einladungen angeklickt: **genau zwei Zeilen mit `?token=`**, eine pro
Klick. Vorher stand der Token in der Anfragezeile *jedes* Seitenaufrufs dieser Umfrage und zusätzlich
im `Referer` jeder Unteranfrage – auch das gemessen, im Browser: die Referrer-Policy sendet für
gleichherkünftige Anfragen die **vollständige** URL samt Query-String.

Wenn dieser vhost ein Access-Log schreibt, schließt ein eigenes `log_format` den Rest:

```nginx
log_format ohne_args '$remote_addr - $remote_user [$time_local] '
                     '"$request_method $uri $server_protocol" $status $body_bytes_sent '
                     '"-" "$http_user_agent"';
```

Zwei Dinge daran sind Absicht: `$uri` statt `$request` lässt den Query-String weg, und `"-"` statt
`$http_referer` ist die Konsequenz daraus – ein Referer aus einer fremden Seite kann eigene
Geheimnisse tragen, und für diese App braucht ihn niemand.

**Zu prüfen:** schreibt der vhost überhaupt ein Access-Log, und wie lange wird es aufbewahrt? Falls
`access_log off` gilt, ist der Punkt gegenstandslos. Wenn es eines gibt, sind die Tokens **alter**
Einladungen darin bereits enthalten – die neue Formatzeile wirkt nur nach vorn.

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

### C5. Ein systemd-Timer für den getakteten Mailversand — **jetzt nötig**

⚠️ **Der Versand ist gebaut, der Timer fehlt. Ohne ihn verschickt Produktion nach dem Deploy
gar keine Mail mehr** — `create()` reiht nur noch ein. Das ist der einzige Punkt in dieser Datei,
der aus einer Änderung von mir zwingend folgt.

Gebraucht wird ein Timer plus Service, der als der demockrazy-Nutzer

```bash
DJANGO_SETTINGS_MODULE=demockrazy_config manage.py send_pending_mails
```

aufruft, im Minutentakt, mit Schreibzugriff auf `/var/lib/demockrazy` (die Datenbank und eine
Sperrdatei daneben). **Mehr nicht:** kein Broker, kein Daemon, kein zusätzliches Python-Paket. Der
Command sperrt sich selbst, ein Timer-Aufruf in einen laufenden Versand hinein beendet sich sofort.

#### Fertig zum Einsetzen

**Gehört ins Modul, nicht in die Node-Config** — es braucht `${djangoenv}` und `${pkg}`, und die
kennt nur das Modul. Zwei Werte kann ich nicht wissen, sie sind mit `@…@` markiert.

**Ausgewertet, nicht nur hingeschrieben:** ich habe das gegen die gepinnte nixpkgs durch
`nixos/lib/eval-config.nix` laufen lassen, mit einem Stellvertreter für den echten Dienst, und die
erzeugten Unit-Dateien gelesen. Dabei ist ein Fehler aufgefallen, den ich sonst geliefert hätte —
siehe der Kommentar bei `removeAttrs`.

```nix
{ config, ... }:

let
  # ⟨1⟩ Genau die Invocation, die im `preStart` des bestehenden Dienstes schon steht -- dort läuft
  # damit `migrate` und `collectstatic`. Im Modul sieht sie aus wie
  # "${djangoenv}/bin/python ${pkg}/share/demockrazy/manage.py". Diese Zeile von dort übernehmen.
  manage = "@MANAGE_PY_INVOCATION@";
in
{
  systemd.services.demockrazy-mail = {
    description = "demockrazy: wartende Umfrage-Mails getaktet verschicken";

    # Nach dem Webdienst einordnen **und ihn mitziehen**: dessen `preStart` ruft `migrate`, und die
    # Warteschlangentabelle entsteht erst dort. Ohne das läuft der erste Timer-Aufruf nach einem
    # frischen Deploy in "no such table: vote_outgoingmail".
    # `wants` statt `requires`: ist der Webdienst kaputt, soll das hier nicht zusätzlich als Fehler
    # im Journal stehen.
    wants = [ "demockrazy.service" "network-online.target" ];
    after = [ "demockrazy.service" "network-online.target" ];

    # Die Umgebung vom bestehenden Dienst **übernehmen statt abschreiben**. Darin steckt
    # DJANGO_SETTINGS_MODULE=demockrazy_config und der PYTHONPATH, über den das generierte
    # Settings-Modul überhaupt gefunden wird -- das liegt nicht im Store der App. Abschreiben würde
    # beim nächsten Modul-Umbau still auseinanderlaufen.
    #
    # `PATH` muss dabei heraus, und das ist nicht Kosmetik: **NixOS setzt `environment.PATH` für
    # jeden Dienst selbst** (aus `path`), und ein mitgeerbter Wert kollidiert damit. Ohne das
    # `removeAttrs` bricht die Auswertung ab mit „The option
    # `systemd.services.demockrazy-mail.environment.PATH` has conflicting definition values".
    # Ausprobiert, nicht überlegt.
    environment = builtins.removeAttrs config.systemd.services.demockrazy.environment [ "PATH" ];
    inherit (config.systemd.services.demockrazy) path;

    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${manage} send_pending_mails";

      # ⚠️ Der wichtigste Wert in diesem Block. systemd bricht einen `oneshot` nach
      # `DefaultTimeoutStartSec` ab -- üblicherweise 90 s. Ein getakteter Lauf ist absichtlich
      # langsam: 100 Empfänger brauchen mit 2 s Pause ~7 s, mit 60 s Pause aber ~3,5 Minuten. Der
      # Default würde ihn also genau dann töten, wenn man die Pause hochsetzt, weil der Mailserver
      # drosselt -- im ungünstigsten Moment. 20 Minuten sind großzügig und trotzdem endlich;
      # endlich muss es sein, weil der Command eine Sperre hält, solange er läuft.
      TimeoutStartSec = "20min";

      # Wie beim Webdienst: Code aus dem read-only Store, beschreibbar nur der State. Gebraucht
      # wird das für die Datenbank, ihre WAL-Dateien und die Sperrdatei daneben
      # (/var/lib/demockrazy/db.mailsend.lock).
      ProtectSystem = "full";
      ReadWritePaths = [ "/var/lib/demockrazy" ];

      # ⟨2⟩ Dieselbe Identität wie der Webdienst -- sonst gehören die WAL-Dateien nach einem Lauf
      # jemand anderem und die uwsgi-Prozesse können nicht mehr schreiben. Werte aus der
      # bestehenden `systemd.services.demockrazy` übernehmen.
      User = "@SAME_USER_AS_THE_WEB_SERVICE@";
      Group = "@SAME_GROUP_AS_THE_WEB_SERVICE@";
    };
  };

  systemd.timers.demockrazy-mail = {
    description = "demockrazy: Mailversand regelmäßig anstoßen";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      # Eine Minute **nachdem der letzte Lauf fertig war**, nicht "jede Minute": ein Lauf kann
      # länger dauern als das Intervall, und dann sollen sich keine Aufrufe stapeln. Die `flock` im
      # Command fängt eine Überlappung ohnehin ab -- das hier vermeidet, dass es dazu kommt.
      OnActiveSec = "1min";
      OnUnitInactiveSec = "1min";
      AccuracySec = "1s";
    };
  };
}
```

Die erzeugte Unit sieht damit so aus (aus der Auswertung, gekürzt):

```ini
[Unit]
After=demockrazy.service network-online.target
Wants=demockrazy.service network-online.target

[Service]
Environment="DJANGO_SETTINGS_MODULE=demockrazy_config"
Environment="PYTHONPATH=…"
ExecStart=…/bin/python …/share/demockrazy/manage.py send_pending_mails
User=demockrazy
Group=demockrazy
ProtectSystem=full
ReadWritePaths=/var/lib/demockrazy
TimeoutStartSec=20min
Type=oneshot
```

#### Drei Dinge, die du prüfen solltest

1. **Benutzt der Dienst `DynamicUser`?** Dann geht das `User`/`Group`-Kopieren nicht, und schlimmer:
   zwei Units mit `DynamicUser` bekommen **verschiedene** UIDs, der Versender könnte die Datenbank
   also nicht beschreiben. In dem Fall braucht es einen statischen Benutzer für beide.
2. **Steht `DJANGO_SETTINGS_MODULE` wirklich in `environment`** des bestehenden Dienstes und nicht in
   einem Wrapper-Skript? Nur dann trägt das Übernehmen es mit. Im Zweifel `systemctl cat
   demockrazy.service` ansehen.
3. **`TimeoutStartSec` nicht weglassen.** systemd bricht einen `oneshot` sonst nach
   `DefaultTimeoutStartSec` ab (üblich 90 s) — und ein getakteter Lauf ist absichtlich langsam.
   Mit `PAUSE=2` sind 100 Empfänger ~7 s, mit `PAUSE=60` aber ~3,5 Minuten: der Default würde genau
   dann töten, wenn man die Pause hochsetzt, weil der Mailserver drosselt.

Von Hand sofort anstoßen geht jederzeit — die Sperre macht das gefahrlos, auch während der Timer
arbeitet:

```bash
systemctl start demockrazy-mail.service
```

Der Entwurf dahinter samt Begründung steht in [plan.md](plan.md) §11.7. Kurz, warum nichts Fertiges:
**es gibt keinen Baustein, der die Arbeit abnimmt.** Nachgesehen (§11.7, 6a): Django 5.2 hat keine
Queue, und das `django.tasks` von Django 6.0 hat nur ein `Immediate`- und ein `Dummy`-Backend – **kein
Datenbank-Backend und keinen Worker**. Man bekäme die API und müsste alles darunter selbst schreiben.
**Celery** und **RQ** brauchen einen Broker als zusätzlichen Dienst auf der Node, **huey** einen
dauerhaft laufenden Consumer. Für hundert Mails im Minutentakt ist ein Timer das Kleinere, und die
Datenbank ist schon da.
*(An den Paketen liegt es nicht – `django-tasks`, `celery`, `huey`, `rq`, `django-q2` liegen alle in
der gepinnten nixpkgs. Das hatte ich vorher falsch behauptet.)*

Zwei Einstellungen steuern die Taktung, beide mit deinen Zahlen als Default:
`DEMOCKRAZY_MAIL_BATCH_SIZE=30` und `DEMOCKRAZY_MAIL_BATCH_PAUSE=2`. **Falls die `450` im Log wieder
auftauchen, ist die Pause die Schraube** – siehe die Rechnung in [plan.md](plan.md) §11.7 und **F20**.

Gemessen mit deinen Zahlen: 101 Mails, 4 Batches, **7,2 s**. Mit `PAUSE=60` wären es ~3,5 Minuten.

Zum Prüfen nach dem Deploy, ohne etwas zu verschicken:

```bash
DJANGO_SETTINGS_MODULE=demockrazy_config manage.py send_pending_mails --pause 0
```

Bei leerer Warteschlange sagt er `0 verschickt, 0 aufgegeben, 0 warten noch (0 Batches).` — dann
sind Pfade, Rechte und die Sperrdatei in Ordnung. Die Sperrdatei entsteht neben der Datenbank, also
als `/var/lib/demockrazy/db.mailsend.lock`; das Verzeichnis muss beschreibbar sein (ist es, dort
liegt die Datenbank).

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

⚠️ **Mit `--fail-level WARNING` fahren** – aus dem Review, Befund R9-2: ohne die Option beendet sich
`manage.py check` bei einem `Warning` mit **0** (gemessen), die Zeile oben hätte also in einem Skript
nichts geprüft. **Behoben ist das im Repo** (R9-1/R9-2: der Check sieht jetzt auf den *Wert*, und die
CI fährt mit dem Flag), für den Aufruf gegen die echten Prod-Settings gilt es weiter:

```bash
DJANGO_SETTINGS_MODULE=demockrazy_config python3 manage.py check --fail-level WARNING
```

Gemessen mit `transaction_mode="DEFERRED"`: `SystemCheckError`, Rückgabecode **1**. Ohne das Flag war
es Rückgabecode 0 bei identischer Ausgabe.

**Nicht** zum `Error` gemacht, obwohl das die Alternative war und in Produktion mehr fangen würde:
ein `Error` lässt `migrate`/`collectstatic` im `preStart` abbrechen, der Dienst käme also nach einem
Deploy mit verlorener Option **nicht mehr hoch**. Das ist eine Betriebsentscheidung – wenn dir
„startet nicht mit klarer Meldung" lieber ist als „läuft und verliert Stimmen an Lock-Fehler", sag es,
dann wird `Warning` zu `Error` (eine Zeile in `demockrazy/checks.py`).

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

### D5. Vor einem Rollback hinter `0004`: die Warteschlange leeren — aus dem Review, Befund R9-3

Der Rückwärtsweg der Migrations läuft sauber (gemessen: `migrate vote 0002` und wieder vorwärts,
beides fehlerfrei). `0004` rückwärts ist aber ein `DROP TABLE vote_outgoingmail` – **liegen dann
Einladungen in der Warteschlange, sind sie weg**, und deren Tokens erfährt niemand mehr. Die Umfrage
schließt dann nie von selbst; der Ersteller muss sie von Hand beenden.

```bash
nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 \
  "SELECT count(*) FROM vote_outgoingmail;"
```

Steht dort etwas anderes als `0`, vorher `send_pending_mails` leerlaufen lassen.

### D6. Falls der Mailversand stillsteht, ohne dass eine `450` im Log steht — aus dem Review, R5-1

Ein Umfragetitel mit einem Zeilenumbruch (über einen rohen POST einsetzbar, das Formular lässt ihn
durch) macht die Nachricht unversendbar: Django wirft `BadHeaderError`, der Versender fängt ihn
nicht, und weil die Zeile die vorderste der Warteschlange ist, stirbt **jeder** folgende Timer-Lauf
an derselben Stelle – auch für alle anderen Umfragen. Erkennbar an einem Traceback im Journal:

```bash
journalctl -u demockrazy-send-mails --since '-1h' | grep -i 'BadHeaderError'
```

Sofortmaßnahme, bis der Befund behoben ist (7.2): die betroffene Zeile löschen.

```bash
# Erst ansehen (die Adresse steht in dieser Zeile -- also nur so weit lesen wie nötig):
nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 \
  "SELECT id, replace(subject, char(10), '\\n') FROM vote_outgoingmail ORDER BY id LIMIT 3;"
```
