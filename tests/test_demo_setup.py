# SPDX-License-Identifier: AGPL-3.0-only
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import test_applications as fixtures
from django.core.management import call_command
from django.test import TransactionTestCase

from farmcredit.interfaces.web.management.commands.demo import ensure_database


class DemoSetupTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp

    def test_existing_database_and_officer_are_preserved(self):
        password = self.officer.password
        # Uses the test runner's PostgreSQL database; creates nothing in the real database.
        ensure_database()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tools/weather-mcp").mkdir(parents=True)
            (root / "tools/weather-mcp/uv.lock").touch()
            with (
                patch(
                    "farmcredit.interfaces.web.management.commands.demo.Path.cwd", return_value=root
                ),
                patch(
                    "farmcredit.interfaces.web.management.commands.demo.subprocess.run"
                ) as install,
                patch("builtins.input", return_value=self.officer.username),
                patch.dict(
                    "os.environ",
                    {"OPENROUTER_API_KEY": "test-only", "FARMCREDIT_SECRET_KEY": "test-only"},
                ),
            ):
                call_command("demo", no_server=True, stdout=StringIO())
                install.assert_called_once()
        self.officer.refresh_from_db()
        self.assertEqual(self.officer.password, password)
        self.assertEqual(type(self.officer).objects.count(), 1)
