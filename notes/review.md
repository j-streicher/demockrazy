# Umfassendes Review

> **Status: noch nicht gelaufen.** Der User gibt das Startsignal. Bis dahin enthält diese Datei nur
> Umfang, Vorgehen und Kriterien — **keine Befunde**. Angelegt 2026-08-04.
>
> Geplant in [plan.md](plan.md) §14. Befunde kommen hierher, Handlungspunkte außerhalb des Repos
> nach [to-check.md](to-check.md).

---

## 1. Umfang

**Der ganze Branch: `master..HEAD`, 78 Commits, plus der Ist-Zustand.**

Beides, und das ist Absicht: ein Diff zeigt Änderungen, aber nicht, was jemand *nicht* geändert hat
und hätte ändern müssen; ein Blick nur auf den Endzustand übersieht, was unterwegs eingeschleppt
wurde. Konkret:

- der Anwendungscode (`vote/`, `demockrazy/`), Templates, Migrations, Management-Command
- die Testsuite selbst — **Tests sind Prüfgegenstand, nicht Prüfinstanz** (§2, Regel 4)
- Konfiguration: `settings.py`, `dev_settings.py`, `test_settings.py`, `pyproject.toml`, `flake.nix`,
  `.gitignore`, CI-Workflow
- die vendorten Assets samt `PROVENANCE.md`
- die Notizen — auf Richtigkeit, nicht auf Vollständigkeit
- die **Deployment-Schnittstelle**: alles, was still verlorengehen kann, weil `demockrazy_config`
  Einstellungen überschreibt (die B16-Klasse von Fehlern)

**Außerhalb des Umfangs, weil ich es nicht sehen kann** (Arbeitsregel 10): das NixOS-Modul, das
Colmena-Repo, der Proxy-vhost, die Prod-Node. Was dort zu prüfen wäre, wird als Frage formuliert und
landet in [to-check.md](to-check.md), nicht als Befund hier.

## 2. Vorgehen — fünf Regeln, die das Review überhaupt erst belastbar machen

1. **Ich habe das alles selbst geschrieben.** Ein Review der eigenen Arbeit ist wertlos, wenn es
   bestätigen will. Die Gegenmaßnahme ist keine Haltung, sondern eine Liste: §3 zählt die
   Fehlerklassen auf, die in *diesem* Projekt schon real vorgekommen sind. Sie werden gezielt
   gesucht, nicht abgewartet.
2. **Jeder Befund ist entweder gemessen oder als ungemessen markiert.** Kein „könnte
   problematisch sein". Entweder steht eine Reproduktion dabei (Befehl, Testfall, Zahl) oder
   ausdrücklich **„gelesen, nicht gemessen"**. Beides ist zulässig, das Vermischen nicht.
3. **Keine Reparatur während des Reviews.** Wer im Vorbeigehen behebt, verliert den Nachweis, dass
   es den Befund gab, und hört auf zu suchen. Erst die vollständige Liste, dann eigene Commits pro
   Befund — mit Verweis auf die Nummer hier.
4. **Negativraum wird protokolliert.** Zu jedem Kriterium steht am Ende, *wie* geprüft wurde, auch
   wenn nichts gefunden wurde. Ein Review ohne diesen Teil ist nicht nachprüfbar: „keine Befunde"
   und „nicht hingesehen" sehen sonst gleich aus.
5. **Wo ich das Ergebnis nicht kenne, wird gemessen, nicht geschlossen.** Das ist Arbeitsregel 4 und
   hat in diesem Projekt mehrfach falsche Schlüsse verhindert.

## 3. Die Fehlerklassen dieses Projekts — gezielt zu suchen

Nicht abstrakt, sondern was hier **schon passiert ist**. Die beste Vorhersage für den nächsten Fehler
ist der letzte:

| # | Klasse | Wo sie herkommt |
|---|---|---|
| K1 | **Still wirkungslose Konfiguration** — steht da, wird nie gelesen | B16 (`ATOMIC_REQUESTS` zehn Jahre modulweit), 5.4 (SQLite-`OPTIONS` gehen über `demockrazy_config` verloren) |
| K2 | **Template-Fallen, die keinen Fehler erzeugen** | B17 (mehrzeilige `{# #}`) — sauberer 200, kaputte Seite, `curl` sah gut aus |
| K3 | **Werkzeug schluckt etwas stillschweigend** | B18 (`.gitignore: static/` verschluckte Assets), `git add` verweigerte ohne `-f` |
| K4 | **Prüfung, die nicht prüft** | Die erste Phase-0-Sonde meldete „IDENTISCH" auf zwei identischen Tracebacks |
| K5 | **Buchhaltungsfehler in eigener Logik** | Der `deferred`-Zähler im ersten Entwurf von `send_pending()` rechnete kumulative Summen gegen eine Batchgröße |
| K6 | **Plausibel begründet und trotzdem falsch** | „Gemeinsame SMTP-Verbindung behebt das Rate-Limit" — sie behebt es nicht; „B legt die Abstimmung still" — tut es erst jenseits des Timeouts |
| K7 | **Framework-Default anders als erwartet** | `EMAIL_TIMEOUT = None` heißt unbegrenzt; `inherit environment` kollidiert mit `environment.PATH` |
| K8 | **Verhaltensänderung, die niemand bestellt hat** | Regel 3/6: Mail-Wortlaut, Token-Längen, URL-Struktur, Feldnamen |

## 4. Kriterien

Reihenfolge ist die Prüfreihenfolge: das Kernversprechen zuerst, Kosmetik zuletzt.

| # | Bereich | Was konkret geprüft wird |
|---|---|---|
| R1 | **Anonymität** (das Kernversprechen) | Gibt es *irgendeinen* Weg von einer Stimme zu einem Wähler? Warteschlange, Token-Cookie, Logs, `django_session`, Migrations-Artefakte, Backups. Was verrät ein Angreifer mit Leserechten auf die DB *während* eines Versands, was danach? |
| R2 | **Authentifizierung / Autorisierung** | Wähler-Token und Management-Token: Erzeugung (Entropie, `SystemRandom`), Vergleich, Verbrauch, Wiederverwendung. Der Cookie-Pfad. Was ohne Token erreichbar ist und ob das gewollt ist (Manage-Seite, `/healthz`, `/vote/create`) |
| R3 | **Eingabeprüfung / Injection** | ORM-Nutzung auf rohes SQL, Template-Autoescaping (**inkl. der Mail-Templates, wo es absichtlich aus ist**), `json_script`, Header-Injection im Mail-Betreff, der eigene URL-Converter, Redirect-Ziele |
| R4 | **Nebenläufigkeit / Datenintegrität** | Vier uwsgi-Prozesse auf einer SQLite-Datei, Versender gegen Stimmabgabe, `F()`-Ausdrücke, `atomic()`-Grenzen, die zwei `UniqueConstraint`s, doppelter Versand, die `flock` (auch: kann sie hängenbleiben?) |
| R5 | **Fehlerbehandlung** | Jedes `except`: was wird geschluckt, was gelogt, was erfährt der Nutzer. Kein Pfad in einen 500. Was passiert bei Ausfall von SMTP, Datenbank, Plattenplatz |
| R6 | **Informationslecks** | Fehlerseiten, Logzeilen (**Adressen? Tokens?**), der 503-Body von `/healthz`, das neue `mails_pending`-Bit, Security-Header |
| R7 | **Missbrauch / DoS** | `/vote/create` ohne Auth: Empfänger-Deckel, aber auch Umfrage-Anzahl, Textlängen, Warteschlangenwachstum, `EMAIL_TIMEOUT`, Laufzeit des Versenders |
| R8 | **Geheimnisse** | `SECRET_KEY`-Pfad und Fallback, nichts Geheimes im Repo, Cookie-Flags, was in Logs und Tracebacks landet |
| R9 | **Migrations & Deploy-Sicherheit** | `0001`–`0004` gegen den Prod-Stand, Reihenfolge, Rückwärtsweg, `preStart`-Verhalten, **die K1-Klasse**: welche Einstellung geht über `demockrazy_config` still verloren |
| R10 | **Testabdeckung und Testqualität** | Was ist *nicht* abgedeckt. Welcher Test besteht auch bei kaputtem Code (K4). Prüfen Tests Wirkung oder Implementierung. Sind die Fixtures ehrlich |
| R11 | **Performance** | Query-Zahlen pro View, N+1, die Warteschlangen-Abfrage, Umfrage-Erstellung bei 150 Empfängern, die Ergebnisseite |
| R12 | **Lieferkette / Lizenzen** | Vendorte Assets gegen `PROVENANCE.md`, die absichtlichen Änderungen daran, nixpkgs-Pinning, CI-Actions, alles MIT/Apache |
| R13 | **Barrierefreiheit** | Formulare, Labels, `aria-*`, das Canvas der Ergebnisseite, Tastaturbedienung, Kontrast |
| R14 | **Lesbarkeit / Wartbarkeit** | Namen, toter Code, Duplikate, **Kommentarlänge** (die Präferenz ist kurz), irreführende Docstrings |
| R15 | **Dokumentation** | README und `notes/` gegen den Code — Stellen, die etwas behaupten, was nicht mehr gilt |

## 5. Befunde

*(Leer. Das Review ist noch nicht gelaufen.)*

Format je Befund:

```
### Rn-1 · Kurztitel
**Schwere:** kritisch | hoch | mittel | niedrig | Notiz
**Ort:** pfad/datei.py:42
**Nachweis:** gemessen (Befehl/Testfall/Zahl) — oder ausdrücklich „gelesen, nicht gemessen"
**Befund:** was falsch ist.
**Folge:** was im Betrieb passiert.
**Vorschlag:** was ich tun würde. Nicht getan — Regel 3.
```

Schweregrade sind für *dieses* Projekt definiert, nicht generisch:

- **kritisch** — verletzt die Anonymität, verliert oder verfälscht Stimmen, oder öffnet die
  Stimmabgabe für Unbefugte.
- **hoch** — Ausfall im Betrieb, Datenleck ohne Stimmbezug, oder etwas, das beim Deploy still bricht.
- **mittel** — falsches Verhalten in einem Randfall, das auffällt und nichts zerstört.
- **niedrig** — Kosmetik mit Folgen, z. B. irreführende Meldung.
- **Notiz** — kein Fehler, aber jemand wird darüber stolpern.

## 6. Negativraum — was geprüft wurde, ohne Befund

*(Leer. Wird beim Lauf gefüllt, ein Absatz je Kriterium: **wie** geprüft wurde und mit welchem
Ergebnis. Ohne diesen Abschnitt ist „keine Befunde" nicht von „nicht hingesehen" zu unterscheiden.)*
