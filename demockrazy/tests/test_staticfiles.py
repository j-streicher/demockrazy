"""Cache busting for static files (plan 4.4).

The test really runs `collectstatic` instead of merely asserting the settings value. The reason: the
failure mode of `ManifestStaticFilesStorage` is not "wrong file name" but **`collectstatic` aborts**
when a CSS file refers via `url()` to something that does not exist. That command runs in production
in `preStart`; an abort there means the service does not start. Exactly that is what CI should see,
and before a new Bootstrap bundle arrives in 4.1.
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
    """The repository defaults, not the test suite's -- that one deliberately reverts them."""
    from demockrazy import settings

    backend = settings.STORAGES["staticfiles"]["BACKEND"]
    assert backend == "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"


def test_collectstatic_resolves_every_reference(tmp_path):
    """Either it runs through, or it says exactly which reference is missing."""
    with override_settings(STATIC_ROOT=tmp_path, STORAGES=MANIFEST_STORAGE):
        call_command("collectstatic", "--noinput", verbosity=0)

        manifest = json.loads((tmp_path / "staticfiles.json").read_text())
        paths = manifest["paths"]

        # One file of our own and one vendored file. Both have to carry a hash and be there.
        # Bootstrap 5 ships its icons as inline data: URIs, so it has no external url() references
        # any more -- with Bootstrap 3 those were the glyphicon fonts. What the test actually caught
        # in 4.1 was the `sourceMappingURL` reference of the bundles to the .map files that are not
        # shipped (see PROVENANCE.md next to them).
        for name in ("css/main.css", "bootstrap-5.3.8-dist/css/bootstrap.min.css"):
            assert paths[name] != name, name
            assert (tmp_path / paths[name]).exists(), name

        # And this is the point of the exercise: the name in the template carries the hash.
        assert static("css/main.css") == f"/static/{paths['css/main.css']}"
