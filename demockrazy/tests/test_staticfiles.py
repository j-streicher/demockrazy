"""Cache-Busting für statische Dateien (Plan 4.4).

Der Test läuft `collectstatic` wirklich, statt nur den Settings-Wert zu behaupten. Grund: der
Fehlerfall von `ManifestStaticFilesStorage` ist nicht „falscher Dateiname", sondern
**`collectstatic` bricht ab**, wenn eine CSS-Datei per `url()` auf etwas verweist, das es nicht
gibt. Das Kommando läuft in Produktion im `preStart`; ein Abbruch dort heißt, der Dienst startet
nicht. Genau das soll die CI sehen, und zwar bevor in 4.1 ein neues Bootstrap-Bundle dazukommt.
"""

import json

from django.core.management import call_command
from django.templatetags.static import static
from django.test import override_settings

MANIFEST_STORAGE = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"},
}


def test_settings_default_to_hashed_names():
    """Die Repo-Defaults, nicht die der Testsuite -- die stellt bewusst zurück."""
    from demockrazy import settings

    backend = settings.STORAGES["staticfiles"]["BACKEND"]
    assert backend == "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"


def test_collectstatic_resolves_every_reference(tmp_path):
    """Läuft durch, oder sagt genau, welche Referenz fehlt."""
    with override_settings(STATIC_ROOT=tmp_path, STORAGES=MANIFEST_STORAGE):
        call_command("collectstatic", "--noinput", verbosity=0)

        manifest = json.loads((tmp_path / "staticfiles.json").read_text())
        paths = manifest["paths"]

        # Eine eigene und eine Vendor-Datei: die zweite ist die, die per url() weiterverweist
        # (Glyphicon-Fonts). Beide müssen einen Hash tragen und wirklich dort liegen.
        for name in ("css/main.css", "bootstrap-3.3.6-dist/css/bootstrap.css"):
            assert paths[name] != name, name
            assert (tmp_path / paths[name]).exists(), name

        # Und das ist der Punkt der Übung: der Name im Template trägt den Hash.
        assert static("css/main.css") == f"/static/{paths['css/main.css']}"
