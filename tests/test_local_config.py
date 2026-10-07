# SPDX-License-Identifier: AGPL-3.0-only
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from farmcredit.interfaces.web.local_config import local_secret


class LocalConfigTests(TestCase):
    def test_signing_key_survives_reload_and_environment_takes_precedence(self):
        with TemporaryDirectory() as directory:
            with (
                patch.dict(os.environ, {}, clear=True),
                patch(
                    "farmcredit.interfaces.web.local_config.Path.cwd", return_value=Path(directory)
                ),
            ):
                first = local_secret()
                self.assertEqual(local_secret(), first)
                self.assertEqual(
                    (Path(directory) / ".local/demo-secret").stat().st_mode & 0o777, 0o600
                )
                with patch.dict(os.environ, {"FARMCREDIT_SECRET_KEY": "explicit-key"}):
                    self.assertEqual(local_secret(), "explicit-key")
                self.assertEqual(local_secret(), first)
