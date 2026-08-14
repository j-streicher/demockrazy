# Commits zusammengefasst – Verfahren, Gruppen, Abwägung

> **Stand: 2026-08-14. Umgesetzt.** Der Branch `update/modernize-2026` hatte 111 Commits über
> `master` und hat jetzt **43** (plus diesen Notiz-Commit). Der Endzustand ist unverändert:
> `git diff pre-squash-2026-08-14 HEAD` ist leer.
>
> **Die 111 Originale mit ihren vollständigen Nachrichten hängen am Tag
> `pre-squash-2026-08-14`** (gepusht). Das ist wichtiger als es aussieht: die neuen Nachrichten sind
> deutlich kürzer als die alten, weil lange Commit-Texte niemand liest (Entscheidung des Users). Was
> gekürzt wurde, ist über den Tag nachlesbar, und die ausführliche Begründung stand ohnehin immer in
> diesen Notizen.

Gewählt wurde **Stufe B** von drei vorbereiteten Stufen: zusammenfassen, was ohnehin zusammengehört,
plus fünf thematisch nahe Blöcke. Was Stufe C zusätzlich gebracht hätte und warum sie nicht
genommen wurde, steht in §6.

## 1. Warum das ging, ohne Nachvollziehbarkeit zu kosten

| Messung | Wert |
|---|---|
| Commits vorher / nachher | 111 / 43 (plus den Notiz-Commit: 44) |
| davon **reine Notiz-Commits** vorher / nachher | **49** (44 %) / **5** |
| Commits, die Code anfassen, vorher / nachher | 62 / 39 |
| `notes/plan.md` war angefasst von | 44 Commits |
| `notes/handover.md` | 35 |
| Verweise auf Branch-Commits per Hash (Notizen, CI) | 92 Stellen, 25 Commits – alle nachgezogen |
| Merge-Commits | 0, der Branch ist linear |
| Review-Kommentare am PR, die der Force-Push verwaisen ließe | 0 (`gh pr view 1`) |

*(Alle Zahlen hier mit Python gemessen, nicht mit `grep` – warum, steht in §7.)*

**49 der 111 Commits waren reine Buchhaltung**: „check off 3.4", „record F17", „refresh the test
count". Sie sind einzeln wertlos und zusammen mit dem Code-Commit, den sie begründen, genau richtig.
**Da kam die Reduktion her, nicht bei den Code-Commits** – von 62 auf 39, und zusammengefasst wurde
dort nur, wo zwei Commits *eine* Änderung in zwei Teilen waren.

**Die 27 Review-Fixes behalten ihre 1:1-Abbildung.** `review.md` führt eine Tabelle mit einer Zeile
je Befund und dem Hash des behebenden Commits; sie zeigt weiterhin auf 16 verschiedene Commits.
Nur zwei Paare teilen jetzt einen (R15-2/R10-5 und R15-3/R15-4), und die gehörten schon vorher
zusammen.

## 2. Verfahren

Alle Gruppen sind **zusammenhängend** – kein Commit wurde umsortiert. Deshalb hat jeder neue Commit
den Baum eines alten, und „jeder Commit verhält sich wie sein Original" gilt unverändert weiter.
Konflikte waren dadurch ausgeschlossen, nicht bloß unwahrscheinlich:

```bash
git tag pre-squash-2026-08-14 && git push origin pre-squash-2026-08-14
git checkout -B squashed master
# je Gruppe: Baum des letzten Original-Commits übernehmen, mit neuer Nachricht committen
git read-tree -u --reset <letzter Commit der Gruppe>
git commit --date=<Autorendatum des ersten Commits der Gruppe> -F <nachricht>
git diff --quiet <letzter Commit der Gruppe> HEAD   # nach jeder Gruppe geprüft
```

Autorendaten sind erhalten, deshalb reicht der Verlauf weiter vom 2026-08-03 bis 2026-08-14.

**Geprüft, nicht geglaubt:** `git diff pre-squash-2026-08-14 HEAD` leer,
`git rev-list --count master..HEAD` = 43, und die volle lokale Schleife grün: `ruff format --check`,
`ruff check`, `check --fail-level WARNING`, `makemigrations --check`, `pytest` → **272 passed**.

„Jeder Commit ist grün" war zunächst ein Argument (gleicher Baum, also gleiches Ergebnis) und ist
jetzt gemessen: `pytest` in einem Worktree an **jedem** Commit des Branches. 44 von 45 grün, mit
**einer Ausnahme, die im Original genauso stand**: der Commit, der die Testsuite anlegt, meldet in
einem frischen Checkout `49 failed, 7 passed, 9 xfailed` -- weil `migrations/` zu diesem Zeitpunkt
noch gitignoriert ist. Genau diese Zahl nennt seine eigene Nachricht („on a fresh clone 49 of 56
fail"), und der nächste Commit committet die Migrations. Ab dort ist jeder Commit grün, mit
wachsender Testzahl bis 272.

## 3. Nacharbeit, die dazugehörte

Ein Rebase vergibt neue Hashes, also zeigten 92 Verweise ins Leere – derselbe Fehler, den das
Review als K5/K6 führt (Prosa beschreibt einen Stand, den es nicht mehr gibt), nur selbst
verursacht. Alle nachgezogen, mit der Tabelle in §5 als Abbildung:

- Die Befundtabelle in `review.md` (27 Zeilen mit Hash) und die Statusblöcke.
- `4e15012` → `90ab23b`, 16-mal referenziert, davon einmal in `.github/workflows/checks.yml`.
- Commitzahlen und -bereiche, die einen Review-Umfang beschreiben („80 Commits", „die sechs Commits
  nach 7.2"): als Messung an einem Tag markiert statt umgeschrieben, mit Verweis auf den Tag.
- Die Stelle in `review.md`, die erklärt, warum ein Hash nicht im eigenen Commit stehen kann: das
  Muster existiert im neuen Verlauf nicht mehr, der Satz sagt das jetzt.
- **Arbeitsregel 1** („Ein Commit = ein Planpunkt") in `plan.md` §3 und `handover.md` §10: das
  Zusammenfassen widerspricht ihr, also trägt sie die Entscheidung mit Datum – wie Regel 3 die
  Ausnahme für deutsche Betriebsausgabe.
- Hash-Verweise **in Commit-Nachrichten** sind durch Beschreibungen ersetzt statt durch neue
  Hashes, damit dieselbe Falle nicht beim nächsten Umschreiben wieder zuschlägt.

Dieser Notiz-Commit ist der letzte: er nennt 43 Hashes, die alle vor ihm liegen. Ein Commit kann
seinen eigenen Hash nicht nennen – dieselbe Zweiteilung, die R15-3 ausgelöst hat.

## 4. Was in eine Gruppe kam, und warum

Regel: ein Notiz-Commit gehört zu dem Code-Commit, den er begründet oder abhakt. Zwei Code-Commits
nur dann zusammen, wenn sie **eine** Änderung waren, die in zwei Teilen kam. Die auffälligsten:

| Gruppe | echte Überschneidung |
|---|---|
| 3 (Toolchain) | `c849562` überschreibt die zwei Zeilen, die `c9b95f1` in `flake.nix` gesetzt hatte; `5ee5580` ist die Folge der ruff-Konfiguration aus `547442b` |
| 8 (Formular) | `9732ded` legt `forms.py` an – **toter Code bis `4bfe022`** |
| 11 (Mail-Service) | `df76af9` korrigiert das Transaktions-Timing des Service, den `53d620f` eben angelegt hatte |
| 17 (Bootstrap) | `cb6af5f` nimmt BS3 weg und legt die BS5-Bundles an, `7d42e2a` schaltet die Vorlagen um – dieselben Dateien |
| 23 (SMTP) | `cdc5ffa` und `9375dac` fassen dieselbe Datei an, beide „die SMTP-Verbindung in Ordnung bringen" |
| 24 (Warteschlange) | `f49d6a5` zeigt den Zustand der Warteschlange, die `1a34a92` gebaut hat – ein Feature |
| 39, 43 | `c7dc26d` und `d9dae03` tragen **nur** einen Hash nach; nach dem Zusammenfassen gegenstandslos |
| 40 (Sprache) | `58e86c5` und `52de7bc` sind die zwei Hälften **einer** Umstellung |

Drei Gruppen mischen etwas, das nicht ganz dazugehört, weil es nicht verschoben werden konnte:
`5f76877` (SQL in den Notizen lauffähig machen) in Gruppe 12, `0b810b3` (Docstring-Korrekturen) in
Gruppe 21, `68ea3f4` (`.gitignore` für `.claude/`) in Gruppe 16 – alle drei hängen an Dateien, die
20 Commits weiter erneut angefasst werden, ein Umsortieren hätte Konflikte riskiert.

## 5. Die Abbildung alt → neu

Vollständig, damit jeder Hash in älteren Notizen, Logs oder Chatverläufen auflösbar bleibt.

| # | neu | Betreff | n | Originale (älteste zuerst) |
|---|---|---|---|---|
| 1 | `8dbe9b5` | notes: plan the modernisation and record the phase-0 baseline | 3 | `1b69f5a` `64b7af5` `30b1e6c` |
| 2 | `90ab23b` | Remove the decommissioned k8s deployment | 2 | `ef68c8c` `4e15012` |
| 3 | `5a9cba0` | Move the toolchain to a flake, add pyproject.toml, and apply ruff | 4 | `c9b95f1` `547442b` `5ee5580` `c849562` |
| 4 | `3435f05` | Add a test suite covering the current behaviour | 3 | `97b7585` `20f3f8c` `c380938` |
| 5 | `42f22f7` | Commit the migrations, reconstructing production's real history | 1 | `93e4394` |
| 6 | `a114cad` | Make the settings defaults safe rather than convenient, and rewrite the README | 6 | `50b9fa3` `0a9cee3` `c87f439` `7fd46f3` `145fe1b` `ff21f11` |
| 7 | `8eb6042` | notes: add a handover document and bring the notes in line with it | 4 | `e18217b` `f365d6a` `e369293` `66b68de` |
| 8 | `b242c02` | Run poll creation through a form, and guard the management token lookup | 5 | `9732ded` `2eb7caa` `4bfe022` `48d87b5` `b339eb2` |
| 9 | `48f8fa9` | Untangle the vote view's error paths | 2 | `d7e8a32` `25be304` |
| 10 | `6eb2b74` | Add a CI workflow that runs the verification loop | 2 | `0b72515` `701398e` |
| 11 | `76a2b07` | Move the poll mails into a service that sends after the transaction commits | 3 | `53d620f` `df76af9` `c0b38e5` |
| 12 | `064c327` | Create polls through a service, in bulk | 3 | `12a24a4` `ae6ce10` `5f76877` |
| 13 | `2d43133` | Tidy up the models, with the constraints the database was missing | 3 | `aa715d3` `5dcecaf` `cc93bda` |
| 14 | `7eb29aa` | Route with path() instead of re_path() | 2 | `5c713b4` `a6651e1` |
| 15 | `5ea0a1a` | Drop a dead setting, add /healthz, and hash the static names | 4 | `bdb0a02` `0f626eb` `a5f53d7` `c5f90c9` |
| 16 | `023c53d` | Fix the template defects and pass the chart its data as JSON (B10, 4.2) | 5 | `c4ee321` `68ea3f4` `010ab0d` `431f309` `0c20e17` |
| 17 | `9edfde0` | Replace Bootstrap 3.3.6 with 5.3.8 and drop jQuery (4.1, 4.2) | 3 | `cb6af5f` `7d42e2a` `60ad6ef` |
| 18 | `1b5a18f` | Cap the number of recipients per poll (B4, 3.8) | 1 | `ed294f1` |
| 19 | `1d0f868` | Replace Highcharts with Chart.js 4.5.1 (B8, 4.3) | 3 | `2423528` `1925abf` `6141533` |
| 20 | `c37b83a` | Harden SQLite for concurrent writers (B13, 5.4) | 2 | `a712776` `80165da` |
| 21 | `fea6311` | notes: add to-check.md, and audit plan.md and handover.md for currency | 3 | `97b005b` `0b810b3` `4c71c16` |
| 22 | `c99b4f7` | Move the voting token out of the URL query string (B9, 3.9) | 2 | `26dcd9f` `b1875ce` |
| 23 | `0d78adc` | Send a poll's mails over one bounded SMTP connection, and work out the pacing | 6 | `cdc5ffa` `3f2137d` `9375dac` `99e630e` `d767d00` `51fd360` |
| 24 | `78d7af0` | Send poll mails from a paced queue, and show the creator that they are queued | 6 | `1a34a92` `4caee19` `f1b1e35` `f49d6a5` `847ee5d` `2367200` |
| 25 | `2e923af` | notes: plan and run the comprehensive review (7.1) | 3 | `49e4c5d` `d257fa5` `b50f5a4` |
| 26 | `ae4a744` | Let the token consumption decide whether a vote counts (R4-1) | 1 | `a1b5117` |
| 27 | `c17b80a` | Stop a single unsendable mail from halting all delivery (R5-1) | 1 | `af30fa5` |
| 28 | `a61e550` | Check the token from the query string before it becomes a cookie (R3-1) | 1 | `4d6e003` |
| 29 | `9d2db3a` | Cap the sizes /vote/create accepts, not just the recipient count (R7-1) | 1 | `3e89f0c` |
| 30 | `c050286` | Make the hardening check look at the value, and let CI fail on it (R9-1, R9-2) | 1 | `a2b50d4` |
| 31 | `810be34` | Close the five gaps the mutation probe found in the suite (R10-1..R10-3) | 1 | `eff438f` |
| 32 | `421816f` | Shuffle which voter gets which token (R1-2) | 1 | `8c65cd3` |
| 33 | `29ba658` | Log why a mail was rejected, and guard the send loop (R6-1, R5-2) | 1 | `6363cb1` |
| 34 | `0dc0ad4` | Send no-store on the token pages, and count multiple choice in one UPDATE (R6-2, R11-1) | 1 | `5ddd491` |
| 35 | `d4d0942` | Give each page a title, colour the form errors, drop "Total Voters: None" (R13-1, R13-2, R14-1) | 1 | `decb33b` |
| 36 | `aa2beb9` | Correct the comments and README lines that describe an older state (R1-1, R14-2, R15-1) | 1 | `4282901` |
| 37 | `4b1c256` | Collect the token-state numbers in one place (R14-3) | 2 | `9bf0fc7` `ac92123` |
| 38 | `fc9ef06` | Keep the admin from editing vote counts or reading tokens (R2-1) | 3 | `5adb612` `2ad3f19` `3418317` |
| 39 | `930442c` | Test the SMTP rejection a real server sends (R10-4) | 2 | `8b238f6` `c7dc26d` |
| 40 | `9c8f90b` | Write the code's prose in English, and keep the operational output German | 4 | `58e86c5` `52de7bc` `65de949` `565abc1` |
| 41 | `a884321` | review: a second pass over the commits after 7.2 | 1 | `6f14184` |
| 42 | `bee388f` | Give the fake mail server a time window and real strictness (R15-2, R10-5) | 2 | `05b4f7d` `57574b9` |
| 43 | `973860d` | notes: bring the notes up to the current state (R15-3, R15-4) | 5 | `4773adc` `02b0fa1` `d9dae03` `8487d2f` `90d22ff` |

## 6. Was nicht gemacht wurde, und warum

- **Stufe C, auf 31–32 Commits.** Sie hätte die Review-Fixes paarweise zusammengefasst: R4-1 mit
  R5-1, R3-1 mit R7-1, R9-x mit R10-x, die drei Mail-Fixes, die vier Seiten-Fixes. Dann zeigen fünf
  Zeilen der Befundtabelle auf Commits mit drei bis fünf unverwandten Fixes. Diese 1:1-Abbildung
  ist das Belastbarste am ganzen Review, und 43 statt 31 kostet nichts, was jemand liest.
- **Umsortieren.** Vier Gruppen wären eine Spur sauberer, wenn ein Commit verschoben würde
  (`50b9fa3` hinter die Notizen, `68ea3f4` an den Bootstrap-Block, `c849562` direkt an `c9b95f1`,
  `65de949` an den Mailtrap-Block). Alle vier sind dateidisjunkt, also konfliktfrei möglich. Nicht
  gemacht: mit Verschiebungen hat kein neuer Commit mehr den Baum eines alten, und damit fällt die
  Prüfung „jeder Commit ist grün wie vorher" weg. Der Gewinn wäre eine Betreffzeile, der Verlust
  eine Garantie.
- **`5ee5580` (den ruff-Lauf) getrennt lassen.** Ein reiner Formatierungs-Commit ist beim Lesen
  wertvoll, weil man ihn überspringen kann, und Arbeitsregel 1 verlangt diese Trennung. Er steckt
  trotzdem in Gruppe 3, weil er die unmittelbare Folge der Konfiguration daneben ist – seine
  Messung („alle 21 Fälle byte-identisch") steht in der neuen Nachricht.
- **Die alten Nachrichten wörtlich übernehmen.** Wäre die vollständigste Lösung gewesen: `git
  rebase -i` mit `squash` und leerem Editor hängt alle Originalnachrichten aneinander. Ergebnis
  wären Commits mit 150 Zeilen Nachricht. Der Tag macht dasselbe, ohne den Log unlesbar zu machen.

## 7. Nachprüfung der neuen Nachrichten

Die neuen Nachrichten sind Prosa über einen Diff -- also genau die Sorte Text, die das Review als
K5/K6 führt. Deshalb sind sie gegen ihre Commits geprüft, nicht nur gelesen:

- **Mechanisch:** jeder in Backticks genannte Dateipfad existiert im Baum des Commits, der ihn
  nennt (0 Treffer), und keine Nachricht sagt „next commit"/„previous commit" -- Formulierungen,
  die durch das Zusammenfassen falsch geworden wären.
- **Gegen die Diffs:** die in den Nachrichten genannten Bezeichner (`_looks_like_a_token`,
  `VOTE_MAX_CHOICES`, `never_cache`, `pk__in`, `amount_tokens_total`, …) gegen `git show` des
  jeweiligen Commits.
- **Gegen die Originale:** die 14 Einzel-Commits hatte ich neu geschrieben, ohne ihre alte Nachricht
  gelesen zu haben -- die kam in meiner Sammlung nur für Mehrfach-Gruppen vor. Dort steckten die
  Fehler.

**Fünf Aussagen waren sachlich falsch und sind korrigiert:**

| Commit | Was falsch war |
|---|---|
| Empfänger-Deckel | „die Zahl, die man ändern muss, wenn der Mailserver drosselt" -- **genau das Gegenteil** dessen, was der Original-Commit ausdrücklich klarstellt: der Deckel ist Missbrauchsschutz, die zwei Grenzen sind unabhängig. Wer das liest, dreht an der falschen Schraube |
| R7-1 | „max_length auf Titel und Beschreibung" -- der Diff setzt es auf **Beschreibung und Choices**; der Titel war seit dem Formular-Commit gedeckelt |
| R10-1..3 | „fünf Lücken, jede hier gedeckt" -- vier sind hier gedeckt, die fünfte gehört zum System-Check des Commits davor, weil die Suite auf `:memory:` läuft |
| R1-1/R14-2 | listete den `deliver()`/`on_commit`-Kommentar mit, der im Shuffle-Commit korrigiert wurde, und zählte die fehlenden `DEMOCKRAZY_*`-Variablen mit vier statt sechs von elf |
| zweiter Lauf | stellte R15-4 in denselben Commit wie R15-3 -- R15-4 entstand erst beim Beheben und steht im letzten Notiz-Commit |

Dazu acht Ungenauigkeiten (eine als „gemessen" ausgegebene qualitative Aussage, eine Tokenprüfung
als „genau 128 Zeichen" statt der tatsächlichen Grenze von 256, ein fehlender Latenz-Vorbehalt bei
R6-2) und drei Commits, in denen eine mitgefahrene Datei unerklärt blieb (`.gitignore` für
`.claude/`, die SQL-Notizen, die vier gelöschten Mail-Settings mit F17).

Eine Korrektur habe ich **verworfen**, weil sie keine war: `review.md` nennt für R15-1 vier
fehlende `DEMOCKRAZY_*`-Variablen, der Fix-Commit sechs von elf. Beides stimmt -- als der Befund
geschrieben wurde, existierte `DEMOCKRAZY_MAX_CHOICES` noch nicht, das kam mit R7-1 dazwischen.
Fast hätte ich eine richtige Zahl „korrigiert".

Der Preis dieser Runde: alle 43 Hashes haben sich noch einmal geändert, also war die Abbildung in §5
und die 92 Verweise aus §3 ein zweites Mal nachzuziehen -- mechanisch, mit derselben Abbildung.

**Eine Ungenauigkeit bleibt bewusst stehen:** der Shuffle-Commit korrigiert nebenbei einen der vier
Kommentare aus R14-2 (den `deliver()`/`on_commit`-Satz), und seine Nachricht sagt das nicht. Die
Zeile in der Befundtabelle nennt jetzt beide Commits und welche Stelle wo behoben ist -- das kostet
kein weiteres Umschreiben der History für einen Satz.

## 8. Und dann war das Messwerkzeug selbst falsch

Die Zahl „58 reine Notiz-Commits" in §1 stand hier zwei Runden lang und war falsch; es sind **49**.
Nicht verrechnet, sondern falsch gemessen: **`grep` ist in dieser Agent-Shell eine Funktion**, die
auf einen `ugrep`-Wrapper mit `--ignore-files --hidden -I --exclude-dir=…` umleitet, und der
antwortet auf Pipe-Eingaben mit anderen Exit-Codes als coreutils. Nachgestellt:

```bash
printf 'README.md\nnotes/x.md\n' | grep -qv '^notes/'   # exit 1  <- die Shell-Funktion
printf 'README.md\nnotes/x.md\n' | /usr/bin/grep -qv '^notes/'   # exit 0  <- richtig
```

Die Zählschleife fragte `if ! echo "$files" | grep -qv '^notes/'` -- also „keine Datei außerhalb von
`notes/`". Mit dem falschen Exit-Code wurden neun Commits als reine Notiz-Commits gezählt, die
`README.md`, `vote/tests/mailtrap.py` oder `demockrazy/checks.py` anfassen. Aufgefallen ist es nur,
weil dieselbe Frage später in Python gestellt wurde und 49 statt 58 herauskam; ohne diese zweite
Messung stünde die falsche Zahl weiter da.

Deshalb sind alle Zahlen in §1 und §3 in Python nachgemessen. Korrigiert wurden: 58 → 49 reine
Notiz-Commits, „von 53 Code-Commits sind 41 übrig" → 62 auf 39, „26 Commits" → 25 referenzierte
Commits, „15-mal" → 16-mal für den k8s-Commit. Unverändert bestätigt: 92 Verweise, 44/35 Commits auf
plan.md/handover.md, 29 Befundzeilen mit 27 Hashes auf 16 Commits, sechs CI-Schritte.

**Die Lektion ist die von K4, eine Ebene höher:** nicht nur der Code unter dem Test kann falsch
sein, sondern das Werkzeug, mit dem geprüft wird. Es ist das zweite Mal in diesem Projekt -- das
erste Mal war der ausgelaufene `cd`, der zwei HTML-Dumps aus demselben Zustand zog (review.md §8.1).
Und beim Nachmessen für §9 kam ein drittes Mal dazu: eine `sed`-Extraktion mit gierigem `.*` schnitt
aus „272 passed" ein „2 passed", also aus jeder Zahl die erste Stelle. Aufgefallen, weil „2 passed"
für HEAD offensichtlich falsch war -- eine Zahl, deren richtigen Wert man kennt, ist der billigste
Test für das Werkzeug. Wer eine Zahl aufschreibt, sollte sie mit zwei verschiedenen Werkzeugen
bekommen haben, oder das Werkzeug an einem Fall prüfen, dessen Antwort er kennt.

## 9. Und der Code selbst?

Das Umschreiben hat **keine Codezeile angefasst**. Gemessen statt behauptet:
`git diff pre-squash-2026-08-14 HEAD -- . ':(exclude)notes'` ergibt genau eine Zeile Unterschied,
den Hash in einem Kommentar von `.github/workflows/checks.yml`. Der geprüfte Zustand und der
gepushte Zustand sind dieselben.

Weil das leicht zu behaupten und schwer zu glauben ist, danach noch einmal von vorn gemessen:

| Prüfung | Ergebnis |
|---|---|
| `nix flake check` | grün |
| `ruff format --check`, `ruff check` | grün |
| `check --fail-level WARNING`, `makemigrations --check` | keine Befunde, keine Drift |
| `pytest` | **272 passed** |
| `pytest` an jedem der 45 Commits | 44 grün, die eine Ausnahme oben erklärt |
| R4-1-Sonde, 100 Runden mit echten Threads | **0 von 100** Doppelstimmen (vor dem Fix: 4 von 100) |

Und die stärkste Prüfung, die dieses Projekt kennt, noch einmal gefahren: **sieben Mutationen, alle
sieben von der Suite bemerkt** -- darunter die vier, die im ersten Review-Lauf *unbemerkt*
durchgingen und deren Lücken 7.2 geschlossen hat.

| Mutation | Folge |
|---|---|
| Token-Löschung ist nicht mehr die Bedingung (R4-1) | 18 Tests rot |
| `@vary_on_cookie` entfernt (R10-1) | 1 rot, in `test_views.py` |
| `SystemRandom` → `random.choice` (R10-2) | 1 rot, in `test_models.py` |
| Batch-Default 30 → 1000 (R10-3) | 1 rot, in `test_mail_service.py` |
| `SMTPResponseException` aus dem `except` (R10-4) | 1 rot -- der Socket-Test, und nur er |
| Token-Shuffle entfernt (R1-2) | 1 rot |
| Zeitfenster des Fake-Servers setzt nie zurück (R15-2) | 2 rot, in `test_mailtrap.py` |

Der Arbeitsbaum war nach jeder Mutation wieder sauber (`git status --porcelain` leer).
