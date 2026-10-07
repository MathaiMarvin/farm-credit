# SPDX-License-Identifier: AGPL-3.0-only
from django import template

from farmcredit.interfaces.web.presentation import display_data, display_text

register = template.Library()
register.filter("ui_text", display_text)
register.filter("ui_data", display_data)
