# SPDX-License-Identifier: AGPL-3.0-only
"""Content versions prevent old browser assets from styling new templates."""

from hashlib import sha256
from pathlib import Path

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static

register = template.Library()


@register.simple_tag
def asset_url(name: str) -> str:
    path = finders.find(name)
    if path is None:
        raise ValueError(f"Missing packaged asset: {name}")
    version = sha256(Path(path).read_bytes()).hexdigest()[:16]
    return f"{static(name)}?v={version}"
