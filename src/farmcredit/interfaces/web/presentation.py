# SPDX-License-Identifier: AGPL-3.0-only
"""UI wording only; never use these helpers for evidence or calculation inputs."""

import re

_ORIGIN_WORDS = re.compile(r"\b(synthetic|fictional|fictitious)\b", re.IGNORECASE)


def display_text(value):
    """Use neutral wording while preserving assumptions and other qualifications."""
    if not isinstance(value, str):
        return value
    return _ORIGIN_WORDS.sub(
        lambda match: "Supplied" if match.group()[0].isupper() else "supplied", value
    )


def display_data(value):
    """Copy a trace for display, excluding origin metadata; retain the stored trace."""
    if isinstance(value, dict):
        return {
            display_text(key): display_data(item)
            for key, item in value.items()
            if key != "synthetic"
        }
    if isinstance(value, (list, tuple)):
        return [display_data(item) for item in value]
    return display_text(value)
