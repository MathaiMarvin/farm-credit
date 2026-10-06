# SPDX-License-Identifier: AGPL-3.0-only
"""Local development entry point: python -m farmcredit.interfaces.web.run."""

import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farmcredit.interfaces.web.settings")
    from django.conf import settings
    from django.core.management import execute_from_command_line

    settings.AUTH_DB.parent.mkdir(parents=True, exist_ok=True)

    args = sys.argv[1:] or ["runserver", "127.0.0.1:8000"]
    execute_from_command_line(["farmcredit", *args])


if __name__ == "__main__":
    main()
