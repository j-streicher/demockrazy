# Chart.js 4.5.1 — Herkunft und die eine Änderung

Ersetzt das vendorte Highcharts 4.2.5, das **proprietär lizenziert** war und damit in einem
MIT-Repo nicht richtig lag (B8). Plan 4.3, Entscheidung F4. Vendored, kein CDN — dieselbe Begründung
wie bei Bootstrap: die Seite soll ohne Fremdverbindung funktionieren.

Chart.js ist **MIT**, der Lizenztext liegt als `LICENSE.md` daneben. Damit ist das Frontend
durchgehend MIT/Apache.

## Quelle

Das offizielle npm-Tarball, nicht ein GitHub-Asset — npm veröffentlicht zu jeder Version einen
`shasum`, die Herkunft ist damit nachprüfbar:

```
https://registry.npmjs.org/chart.js/-/chart.js-4.5.1.tgz
sha1    19dd1a9a386a3f6397691672231cb5fc9c052c35   (von npm veröffentlicht, geprüft)
sha256  f540d98468457ac7a0aabb32006dfb066297e096c5ea063a5d80aa973d1c337a
```

v4.5.1 war am 2026-08-04 die aktuellste Version; gegen die GitHub-Releases **und** die
npm-Registry geprüft, nicht erinnert.

Übernommen wurden **nur zwei Dateien** aus dem Tarball:

| Datei | Herkunft im Tarball | sha256 wie ausgeliefert |
|---|---|---|
| `chart.umd.min.js` | `package/dist/chart.umd.min.js` | `48444a82d4edcb5bec0f1965faacdde18d9c17db3063d042abada2f705c9f54a` |
| `LICENSE.md` | `package/LICENSE.md` | — |

Das **UMD**-Bundle, weil es ohne Modul-Loader in ein `<script>`-Tag passt und `window.Chart` setzt.
Kein Datums-Adapter nötig: der gibt es nur für Zeitachsen, und hier wird ein Tortendiagramm
gezeichnet. Keine `.map`-Dateien, keine ESM-/CJS-Varianten, keine TypeScript-Typen.

## Die eine Änderung: `sourceMappingURL` entfernt

Wie bei Bootstrap (siehe `../bootstrap-5.3.8-dist/PROVENANCE.md`) und aus demselben zwingenden
Grund: `ManifestStaticFilesStorage` löst den Verweis auf und `collectstatic` **bricht ab**, wenn die
`.map`-Datei fehlt. Das Kommando läuft in Produktion im `preStart` — ein Abbruch dort heißt, der
Dienst startet nicht.

Entfernt ist die letzte Zeile der Datei, sonst nichts:

```bash
sed -i '$ d' chart.umd.min.js
```

| Datei | sha256 nach dem Strippen |
|---|---|
| `chart.umd.min.js` | `84d0e233daba702b8f77d669d8c137cad36d441a10f200b6f2d3ab553bdfcf6b` |

## Beim nächsten Upgrade

1. Tarball holen, `sha1` gegen `registry.npmjs.org/chart.js` prüfen, beide Summen hier eintragen.
2. Nur `dist/chart.umd.min.js` und `LICENSE.md` übernehmen, dann `sed -i '$ d'`.
3. Der Verzeichnisname trägt die Version (`chartjs-4.5.1`) und steht in
   `vote/templates/vote/base.html` bzw. `results.html`.
4. `pytest` fährt `collectstatic` mit und merkt, wenn ein Verweis nicht auflöst.
