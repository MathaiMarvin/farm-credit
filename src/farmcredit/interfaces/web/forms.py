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

    price_reduction = forms.DecimalField(
        label="Stress: sale price reduction (%)",
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        initial=20,
        help_text="Explicit test assumption, not a price forecast.",
    )
    harvest_reduction = forms.DecimalField(
        label="Stress: gross harvest reduction (%)",
        min_value=0,
        max_value=100,
        max_digits=5,
        decimal_places=2,
        initial=20,
        help_text="Retained food and losses stay fixed. This is not a yield prediction.",
    )
