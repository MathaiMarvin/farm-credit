# SPDX-License-Identifier: AGPL-3.0-only
"""One-command local setup; synthetic use only, with individually named accounts."""

import os
import secrets
import subprocess
from getpass import getpass
from pathlib import Path

import psycopg
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from psycopg import sql


def ensure_database():
    config = settings.DATABASES["default"]
    parameters = {
        name: config[key]
        for name, key in (
            ("user", "USER"),
            ("password", "PASSWORD"),
            ("host", "HOST"),
            ("port", "PORT"),
        )
        if config.get(key)
    }
    try:
        with psycopg.connect(dbname="postgres", autocommit=True, **parameters) as connection:
            exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", [config["NAME"]]
            ).fetchone()
            if not exists:
                connection.execute(
                    sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config["NAME"]))
                )
    except psycopg.Error as error:
        raise CommandError(
            "PostgreSQL setup failed. Check PG* settings and permission to create the database; no database was dropped."
        ) from error


class Command(BaseCommand):
    help = "Set up the local synthetic demo and start it on loopback; requires uv and PostgreSQL."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-server", action="store_true", help="Complete setup without starting the server."
        )

    def handle(self, *args, **options):
        root = Path.cwd()
        weather = root / "tools/weather-mcp"
        if not (weather / "uv.lock").is_file():
            raise CommandError("Run ./scripts/demo from the repository checkout.")
        self.stdout.write(
            "Setting up the synthetic local demo. Existing accounts and records are preserved."
        )
        subprocess.run(["uv", "sync", "--locked", "--project", str(weather)], check=True)
        ensure_database()
        call_command("migrate", interactive=False)
        local = root / ".local"
        local.mkdir(exist_ok=True)
        secret_file = local / "demo-secret"
        if not os.environ.get("FARMCREDIT_SECRET_KEY"):
            if not secret_file.exists():
                descriptor = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, "w") as handle:
                    handle.write(secrets.token_urlsafe(50))
            settings.SECRET_KEY = secret_file.read_text().strip()
            os.environ["FARMCREDIT_SECRET_KEY"] = settings.SECRET_KEY
        username = input("Officer username (existing or new): ").strip()
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            name = input("Officer's full name: ").strip()
            call_command("createofficer", username, name=name)
        elif (
            not user.is_active
            or not user.get_full_name().strip()
            or not user.has_perm("auth.review_assessment")
        ):
            raise CommandError(
                "That account is not an active named advisory reviewer; choose an authorised account."
            )
        if not os.environ.get("OPENROUTER_API_KEY"):
            key = getpass("OpenRouter key (hidden; blank uses fixed checks only): ").strip()
            if key:
                os.environ["OPENROUTER_API_KEY"] = key
        self.stdout.write(
            "Ready: http://127.0.0.1:8000/applications/ — sign in with your officer account."
        )
        if not options["no_server"]:
            call_command("runserver", "127.0.0.1:8000", use_reloader=False)
