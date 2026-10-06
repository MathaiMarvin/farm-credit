# SPDX-License-Identifier: AGPL-3.0-only
from decimal import Decimal

from django import forms

from farmcredit.adapters.institution_demo import MEMBER_CHOICES
from farmcredit.adapters.market_hdx import MARKET_CHOICES
from farmcredit.adapters.market_kamis import MARKET_CHOICES as KAMIS_CHOICES
from farmcredit.adapters.weather_mcp import WEATHER_CHOICES


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


class ApplicationForm(forms.Form):
    weather_reference = forms.ChoiceField(
        label="Weather reference",
        required=False,
        choices=(("", "No weather reference selected"), *WEATHER_CHOICES),
        help_text="Select only when this reference is relevant. City-level model forecasts cannot establish exact farm conditions or predict the whole crop season.",
    )
    kamis_market_reference = forms.ChoiceField(
        label="Additional KAMIS reference",
        required=False,
        choices=(("", "No KAMIS reference selected"), *KAMIS_CHOICES),
        help_text="Separate public dry-maize quotation; reuse licence unverified. No price is substituted if the selected market has no matching quote.",
    )
    market_reference = forms.ChoiceField(
        label="Market price reference",
        required=False,
        choices=(("", "No reference market selected"), *MARKET_CHOICES),
        help_text="Historical wholesale context, not a buyer offer or farm-gate forecast. Retrieval occurs when you investigate; the assumed sale price stays unchanged.",
    )
    institution_record_set = forms.ChoiceField(
        label="Synthetic institution file",
        required=False,
        choices=(("", "No matched institutional file"), *MEMBER_CHOICES),
        help_text="Explicitly link this synthetic household to its demo cooperative records. Names are never used to guess a match.",
    )
    farmer = forms.CharField(label="Synthetic household reference", max_length=100)
    farm = forms.CharField(label="Farm / plot reference", max_length=200, required=False)
    location = forms.CharField(label="Farm location", max_length=200, required=False)
    season = forms.CharField(label="Season", max_length=100, required=False)
    crop = forms.ChoiceField(
        choices=[("maize", "Maize"), ("other", "Other — unsupported for calculation")]
    )
    area_hectares = forms.DecimalField(
        label="Plot area (hectares)",
        required=False,
        min_value=Decimal("0.01"),
        max_digits=10,
        decimal_places=2,
    )
    repayment_mode = forms.ChoiceField(
        choices=[("seasonal", "One seasonal payment"), ("monthly", "Supplied instalments")]
    )
    schedule = forms.CharField(
        label="Supplied repayment schedule",
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One line per payment: record ID, YYYY-MM-DD, amount in KSh. Use positive amounts. Leave blank if unknown; no interest or schedule is generated.",
    )
    schedule_source = forms.CharField(label="Schedule source", max_length=300, required=False)
    schedule_version = forms.CharField(label="Schedule version", max_length=100, required=False)
    collection_method = forms.CharField(label="Collection method", max_length=200, required=False)
    cash_records = forms.CharField(
        label="Other household cash records",
        required=False,
        max_length=10000,
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One line: record ID, YYYY-MM-DD, signed KSh amount. Income is positive; expenses and existing obligations are negative. Exclude this loan's repayments and harvest sale. Confirm coverage separately, including when no other cash movements are due.",
    )
    available_records = forms.CharField(
        label="Available records and unresolved questions",
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )
    source = forms.CharField(
        label="Source of supplied values",
        required=False,
        max_length=300,
        help_text="Describe the synthetic record or explicit assumption behind these values. Leave blank when the source is unknown.",
    )
    recorded_on = forms.DateField(
        label="Source recording date",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    basis = forms.ChoiceField(
        label="Evidence basis",
        required=False,
        choices=[
            ("", "Unknown — request evidence"),
            ("declared", "Declared"),
            ("assumed", "Assumed"),
            ("observed", "Observed in a synthetic record"),
        ],
    )

    def __init__(self, *args, **kwargs):
        from farmcredit.application.intake import INTAKE_FIELDS

        super().__init__(*args, **kwargs)
        for path, unit, label in INTAKE_FIELDS:
            self.fields[path.replace(".", "_")] = (
                forms.DateField(
                    label=label, required=False, widget=forms.DateInput(attrs={"type": "date"})
                )
                if unit == "date"
                else forms.DecimalField(
                    label=label, required=False, min_value=0, max_digits=14, decimal_places=2
                )
            )
        self.order_fields(
            [
                "farmer",
                "institution_record_set",
                "farm",
                "location",
                "market_reference",
                "kamis_market_reference",
                "weather_reference",
                "season",
                "crop",
                "area_hectares",
                *[p.replace(".", "_") for p, _, _ in INTAKE_FIELDS],
                "repayment_mode",
                "schedule",
                "schedule_source",
                "schedule_version",
                "collection_method",
                "cash_records",
                "available_records",
                "source",
                "recorded_on",
                "basis",
            ]
        )

    def clean(self):
        from django.utils import timezone

        from farmcredit.application.intake import intake_inputs

        data = super().clean()
        if data.get("recorded_on") and data["recorded_on"] > timezone.localdate():
            self.add_error("recorded_on", "The source recording date cannot be in the future.")
        if not self.errors:
            try:
                self.inputs = intake_inputs(data)
            except ValueError as error:
                self.add_error(None, str(error))
        return data
