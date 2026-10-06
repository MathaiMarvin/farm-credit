# SPDX-License-Identifier: AGPL-3.0-only
"""Provision an individually named local reviewer without shared credentials."""

from getpass import getpass

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Create a named officer with advisory-review permission; prompts for a password."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("--name", required=True)

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name or len(name) > 150:
            raise CommandError("Supply the officer's name (1–150 characters).")
        user_model = get_user_model()
        user = user_model(username=options["username"], first_name=name)
        try:
            user.full_clean(exclude=["password"])
            password = getpass("Password: ")
            if password != getpass("Password (again): "):
                raise CommandError("Passwords did not match.")
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error
        with transaction.atomic():
            user.set_password(password)
            user.save()
            permission, _ = Permission.objects.get_or_create(
                content_type=ContentType.objects.get_for_model(user_model),
                codename="review_assessment",
                defaults={"name": "Can review a FarmCredit advisory"},
            )
            user.user_permissions.add(permission)
        self.stdout.write(self.style.SUCCESS(f"Created officer {user.username} ({name})."))
