# SPDX-License-Identifier: AGPL-3.0-only
"""Persistent signing key for the loopback-only development configuration."""

import os
import secrets
from pathlib import Path


def local_secret():
    if configured := os.environ.get("FARMCREDIT_SECRET_KEY"):
        return configured
    path = Path.cwd() / ".local" / "demo-secret"
    path.parent.mkdir(exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        pass
    else:
        with os.fdopen(descriptor, "w") as handle:
            handle.write(secrets.token_urlsafe(50))
    secret = path.read_text().strip()
    if not secret:
        raise ValueError("Local signing key is empty. Set FARMCREDIT_SECRET_KEY before starting.")
    return secret
