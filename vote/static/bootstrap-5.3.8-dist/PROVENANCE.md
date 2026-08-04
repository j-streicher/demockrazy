# Bootstrap 5.3.8 — Herkunft und die eine Änderung

Vendored, absichtlich kein CDN: die Seite soll ohne Fremdverbindung funktionieren, und ein CDN wäre
der einzige externe Host im ganzen Dokument. Plan 4.1, Freigabe F19.

## Quelle

```
https://github.com/twbs/bootstrap/releases/download/v5.3.8/bootstrap-5.3.8-dist.zip
sha256  3258c873cbcb1e2d81f4374afea2ea6437d9eee9077041073fd81dd579c5ba6b
```

v5.3.8 war am 2026-08-04 das aktuellste Release (2025-08-26); gegen die GitHub-API geprüft, nicht
erinnert. Lizenz MIT — passt zum Repo.

Übernommen wurden **nur diese zwei Dateien**, keine Source-Maps, keine ungebündelten oder
unminifizierten Varianten, kein RTL-Build:

| Datei | sha256 wie ausgeliefert |
|---|---|
| `css/bootstrap.min.css` | `d85327d99c7a3ee1f9b5d0500d1370acea3ad2db39c163c2f51f232baedbdede` |
| `js/bootstrap.bundle.min.js` | `e4fd49181388c48ec5040bd3fe66f57c29c8e67fcd8502b3354b96ec7ab47cc7` |

Das `bundle` enthält Popper, deshalb genügt eine JS-Datei. jQuery braucht Bootstrap 5 nicht.

## Die eine Änderung: `sourceMappingURL` entfernt

Beide Dateien enden im Original mit einem Verweis auf ihre Source-Map:

```
/*# sourceMappingURL=bootstrap.min.css.map */
//# sourceMappingURL=bootstrap.bundle.min.js.map
```

Diese Zeile ist **entfernt** — jeweils die letzte Zeile der Datei, sonst nichts:

```bash
sed -i '$ d' css/bootstrap.min.css
sed -i '$ d' js/bootstrap.bundle.min.js
```

| Datei | sha256 nach dem Strippen |
|---|---|
| `css/bootstrap.min.css` | `8f8173cb2d8f867274aeb0cb15328e60f490c7f272351e51a55f1dabb486e4ff` |
| `js/bootstrap.bundle.min.js` | `c6f670216aedd2c61ec83102f7e40c1c44114eecd7f37b2edc332757390c386a` |

**Warum das nötig ist, und zwar nicht aus Ordnungsliebe:** `ManifestStaticFilesStorage` (Plan 4.4)
löst die Verweise in CSS und JS auf und **bricht ab**, wenn das Ziel fehlt. `collectstatic` läuft in
Produktion im `preStart` des systemd-Service — ein Abbruch dort heißt, der Dienst startet nicht.
Gemessen: mit den Verweisen scheitert `collectstatic` mit
`The file 'bootstrap-5.3.8-dist/js/bootstrap.bundle.min.js.map' could not be found`.
Aufgefallen ist es dem Test in `demockrazy/tests/test_staticfiles.py`, der `collectstatic` wirklich
fährt — genau der Fall, für den er geschrieben wurde.

Die Alternative wäre, die Maps mitzuvendoren (~900 KB Debug-Daten für Produktion). Wer sie zum
Debuggen doch will, lädt das Dist-Archiv oben und legt die vier Dateien zusammen wieder hin.

## Beim nächsten Upgrade

1. Neues Dist-Archiv holen, sha256 hier eintragen.
2. Nur die zwei Dateien übernehmen, `sed -i '$ d'` auf beide.
3. Verzeichnisname trägt die Version (`bootstrap-5.3.8-dist`) — er steht in `vote/templates/base.html`
   und in `demockrazy/tests/test_staticfiles.py`.
4. `pytest` fährt `collectstatic` mit und merkt, wenn ein Verweis nicht auflöst.
