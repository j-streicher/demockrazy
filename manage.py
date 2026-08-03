#!/usr/bin/env python3
"""Djangos Kommandozeilen-Werkzeug für administrative Aufgaben."""

import os
import sys


def main():
    # setdefault, nicht zuweisen: in Produktion setzt der systemd-Service
    # DJANGO_SETTINGS_MODULE=demockrazy_config, und `manage.py migrate` bzw. `collectstatic`
    # laufen dort im preStart. Ein hartes Setzen würde die Prod-Settings umgehen.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "demockrazy.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django konnte nicht importiert werden. Ist es installiert und im PYTHONPATH? "
            "Fehlt vielleicht ein `nix develop` oder ein aktiviertes virtualenv?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
