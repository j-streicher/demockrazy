# Phase 2.1 – Migrations einchecken: was gemacht wurde und warum

Erledigt 2026-08-03, Commit „Commit the migrations, reconstructing production's real history".

## Das Problem

`migrations/` stand in [.gitignore](../.gitignore). [vote/migrations/](../vote/migrations/) enthielt nur
`__init__.py`. Konsequenzen:

- **Kein Nachweis im Repo, welches Schema in Produktion liegt.**
- Jede Umgebung erzeugte sich ihre Migration selbst; die [README.md](../README.md) instruierte das
  sogar ausdrücklich (`makemigrations` vor `migrate`).
- Modelländerungen waren nicht reviewbar und nicht reproduzierbar.
- Die Testsuite aus Phase 1 lief **nur lokal**: auf einem frischen Clone fielen 49 von 56 Tests um,
  weil ohne Migration keine Tabellen entstanden.

## Der Prod-Stand (F12, vom User geliefert)

Abgefragt auf `wahlcomputer.mayflower.de`, `/var/lib/demockrazy/db.sqlite3`:

```
app  | name                    | applied
-----+-------------------------+---------------------------
vote | 0001_initial            | 2016-06-09 16:47:52.528528
vote | 0002_auto_20160701_2022 | 2016-07-01 20:22:11.561163
```

**Zwei** angewendete Migrations, nicht eine. Genau der Fall, der beim naiven Einchecken einer
einzelnen `0001_initial` Ärger macht.

Prod-Schema:

```sql
CREATE TABLE "vote_poll" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
  "title" varchar(200) NOT NULL, "question_text" text NOT NULL, "pub_date" datetime NOT NULL,
  "creator_token" varchar(512) NOT NULL, "identifier" varchar(64) NOT NULL,
  "is_active" bool NOT NULL, "num_tokens" integer NULL, "type" varchar(20) NOT NULL);
CREATE TABLE "vote_choice" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
  "choice_text" text NOT NULL, "votes" integer NOT NULL,
  "poll_id" integer NOT NULL REFERENCES "vote_poll" ("id"));
CREATE TABLE "vote_token" ("id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
  "token_string" varchar(128) NOT NULL,
  "poll_id" integer NOT NULL REFERENCES "vote_poll" ("id"));
CREATE INDEX "vote_choice_582e9e5a" ON "vote_choice" ("poll_id");
CREATE INDEX "vote_token_582e9e5a" ON "vote_token" ("poll_id");
```

*Einschränkung: die `type`-Spalte war in der Terminalausgabe abgeschnitten (`"type...`). Position
und Modelldefinition (`CharField(max_length=20, default="simple_choice")`) ergeben
`varchar(20) NOT NULL`, was der frisch migrierte Stand exakt reproduziert. Für letzte Sicherheit:
`nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 "PRAGMA table_info(vote_poll);"`*

## Die Lösung: Historie rekonstruieren statt zusammenfassen

Nicht eine zusammengefasste `0001_initial`, sondern **beide Migrations unter ihren
Originalnamen**:

1. `type` und `num_tokens` temporär aus [vote/models.py](../vote/models.py) entfernt
   → `makemigrations vote --name initial` → [0001_initial.py](../vote/migrations/0001_initial.py)
2. Modell wiederhergestellt → `makemigrations vote --name auto_20160701_2022`
   → [0002_auto_20160701_2022.py](../vote/migrations/0002_auto_20160701_2022.py)
   (fügt `num_tokens` und `type` an)

### Warum das nachweislich richtig ist

Die **Spaltenreihenfolge** von `vote_poll` nach beiden Migrations:

```
id, title, question_text, pub_date, creator_token, identifier, is_active, num_tokens, type
```

Das ist **Zeichen für Zeichen die Reihenfolge der Produktionstabelle**. Eine zusammengefasste
`0001_initial` erzeugt stattdessen `id, title, type, num_tokens, question_text, …` – `type` und
`num_tokens` in der Mitte. Die Aufteilung ist damit nicht geraten, sondern durch das Prod-Schema
bestätigt.

Zusätzlich: `makemigrations --check --dry-run` meldet `No changes detected`, die zwei Migrations
bilden also den aktuellen Modellstand vollständig ab.

## Deploy-Pfad

**`migrate` ist in Produktion ein garantierter No-Op.** Beide Migrationsnamen stehen schon in
`django_migrations`, Django überspringt sie. **Kein `--fake-initial` nötig.**

Gegenprobe nach dem Deploy:

```bash
./manage.py showmigrations vote     # beide mit [X]
./manage.py migrate --plan          # sollte leer sein
```

## Verbleibende Abweichungen (nicht durch Migrations behebbar)

Beide stammen aus der Django-Version, die die Tabellen 2016 angelegt hat, nicht aus den
Migrationsdateien – ein frisches `migrate` mit Django 5.2 erzeugt zwangsläufig das Neue:

| | Prod (2016) | frisch (Django 5.2) |
|---|---|---|
| Fremdschlüssel | `REFERENCES "vote_poll" ("id")` | `… DEFERRABLE INITIALLY DEFERRED` |
| Index `vote_choice` | `vote_choice_582e9e5a` | `vote_choice_poll_id_8401e113` |
| Index `vote_token` | `vote_token_582e9e5a` | `vote_token_poll_id_e1049aa3` |

**Für den ORM irrelevant.** Relevant wird es, wenn eine künftige Migration einen Index über seinen
Namen umbenennt oder löscht – dann schlägt sie in Produktion fehl, weil der Name dort anders ist.
Ebenso ist FK-Prüfzeitpunkt-Verhalten minimal anders (nicht aufgeschoben).

**Konsequenz für Phase 3.6** (dort sollen `UniqueConstraint`s auf `Token.token_string` und
`Poll.identifier` dazukommen): Constraints *hinzufügen* ist unkritisch, aber vorher prüfen, dass
in Prod keine Duplikate liegen, sonst schlägt die Migration beim Anlegen des Unique-Index fehl:

```bash
nix run nixpkgs#sqlite -- -readonly /var/lib/demockrazy/db.sqlite3 \
  "SELECT token_string, COUNT(*) FROM vote_token GROUP BY token_string HAVING COUNT(*) > 1;
   SELECT identifier,   COUNT(*) FROM vote_poll  GROUP BY identifier   HAVING COUNT(*) > 1;"
```

**Nachtrag 3.6 -- teils erledigt, gegen ein Prod-Abbild gemessen.** Die zwei
`UniqueConstraint`s sind mit `0003_model_constraints_and_choices` dazugekommen. Wichtig dabei:
**SQLite kann keinen Constraint an eine bestehende Tabelle anhängen, Django schreibt sie neu**
(CREATE/INSERT/DROP/RENAME) -- ein `CREATE UNIQUE INDEX` gibt es hier nicht. Geprüft auf einer
Datenbank mit genau dem obigen Prod-Schema (alte Indexnamen, nicht-aufschiebbare FKs) und Zeilen in
allen drei Tabellen:

- Migration läuft durch, **alle Zeilen überleben**, `PRAGMA foreign_key_check` ist leer,
  die Spaltenreihenfolge von `vote_poll` bleibt unverändert.
- `vote_poll` bekommt nur den Constraint (die Tabelle hat keine FKs).
- **`vote_token` wird dabei normalisiert:** FK → `DEFERRABLE INITIALLY DEFERRED`, Index
  `vote_token_582e9e5a` → `vote_token_poll_id_e1049aa3`. Das ist genau der Stand, den ein frisches
  `migrate` erzeugt -- die Abweichung aus der Tabelle oben ist für `vote_token` damit **weg**.
- **`vote_choice` bleibt unangetastet** und behält `vote_choice_582e9e5a` und seinen
  nicht-aufschiebbaren FK. Prod ist danach also gemischt. Harmlos, aber zu wissen.
- Duplikate gibt es in Prod keine (vom User geprüft), der Unique-Index kann nicht auflaufen.
- Nebenbei bestätigt: `PRAGMA table_info(vote_poll)` auf Prod liefert genau die Reihenfolge, die
  die zwei rekonstruierten Migrations erzeugen, und `type varchar(20) NOT NULL` an Position 8.
  Damit ist der letzte Rest von F12 erledigt. (`PRAGMA` schreibt Typnamen groß, `.schema` klein --
  kein Widerspruch, nur eine andere Darstellung.)

Kein Nebenläufigkeitsrisiko: das Modul ruft `migrate` im `preStart`, bevor der Dienst startet.

Falls die Index-Namen später wirklich stören: einmalig eine Data-/Schema-Migration mit
`RunSQL`, die die alten Indizes dropt und unter den neuen Namen neu anlegt – aber nur mit
Backup und nur, wenn es einen konkreten Anlass gibt. Nicht vorsorglich.

## Ergebnis

- [notes/baseline-schema.sql](baseline-schema.sql) ist damit überholt (es zeigte den Stand
  einer *zusammengefassten* Migration) – bleibt als Phase-0-Artefakt liegen, die maßgebliche
  Referenz ist ab jetzt dieses Dokument.
- Testsuite auf einem frischen `git clone` verifiziert: **56 grün, 9 xfailed.**
