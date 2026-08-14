#!/usr/bin/env python3
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    # setdefault, not an assignment: in production the systemd service sets
    # DJANGO_SETTINGS_MODULE=demockrazy_config, and `manage.py migrate` and `collectstatic` run
    # there in preStart. Setting it hard would bypass the production settings.
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
