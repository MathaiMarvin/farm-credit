# SPDX-License-Identifier: AGPL-3.0-only
from decimal import Decimal

from django import forms


class ScenarioForm(forms.Form):
    received_on = forms.DateField(
        label="Expected sale receipt date",
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        help_text="When the sale proceeds become available to the household.",
    )
    price_per_kg = forms.DecimalField(
        label="Assumed sale price (KSh/kg)",
        min_value=Decimal("0.01"),
        max_digits=8,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal"}),
        help_text="A synthetic assumption, not a live market quotation.",
    )
