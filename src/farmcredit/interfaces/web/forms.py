# SPDX-License-Identifier: AGPL-3.0-only
from decimal import Decimal

from django import forms

from farmcredit.adapters.institution_demo import MEMBER_CHOICES


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
        help_text="A planning assumption, not a live market quotation.",
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
    weather_reference = forms.CharField(
        max_length=200,
        label="Weather reference",
        required=False,
        help_text="Enter a Kenyan town, for example Kisumu or Eldoret. The agent checks the resolved location before using a seven-day forecast; ambiguous places need clarification. This is not a seasonal yield forecast.",
    )
    kamis_market_reference = forms.CharField(
        max_length=200,
        label="Additional KAMIS reference",
        required=False,
        help_text="Enter the exact market name used by KAMIS, for example Ahero in Kisumu county. The agent matches the recorded crop and market and preserves the variety, grade and price basis.",
    )
    market_reference = forms.CharField(
        max_length=200,
        label="Market price reference",
        required=False,
        help_text="Optional WFP/HDX market name, for example Kisumu. The agent looks for the recorded crop and market; missing coverage stays missing. Historical wholesale context does not replace a buyer offer.",
    )
    institution_record_set = forms.ChoiceField(
        label="Institution file",
        required=False,
        choices=(("", "No matched institutional file"), *MEMBER_CHOICES),
        help_text="Link this household to its cooperative records. Names are never used to guess a match.",
    )
    farmer = forms.CharField(label="Household reference", max_length=100)
    farm = forms.CharField(label="Farm / plot reference", max_length=200, required=False)
    location = forms.CharField(label="Farm location", max_length=200, required=False)
    season = forms.CharField(label="Season", max_length=100, required=False)
    crop = forms.CharField(label="Crop or enterprise", max_length=100)
    production_pattern = forms.ChoiceField(
        label="Production and sale pattern",
        required=False,
        choices=[
            ("", "Not yet established"),
            ("single_harvest", "One harvest, sold by weight"),
            ("recurring", "Repeated sales, livestock or several enterprises"),
        ],
        help_text="Choose the pattern that fits the household. The current calculator models one harvest in kilograms; other patterns can be investigated but need a suitable cash-flow model.",
    )
    cooperative_name = forms.CharField(
        label="Cooperative or lender",
        max_length=200,
        required=False,
        help_text="Name the organisation handling this application. Naming it does not connect its records or apply a lending policy.",
    )
    kamis_classification = forms.CharField(
        label="KAMIS variety / classification",
        max_length=100,
        required=False,
        help_text="If the market lists several varieties, enter the matching classification. Leave blank if unknown; the agent will show which choices need clarification rather than choose a price for you.",
    )
    kamis_county = forms.CharField(
        label="KAMIS market county",
        max_length=100,
        required=False,
        help_text="County where the selected market is located, for example Kisumu. It must match KAMIS’s county catalogue.",
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
        help_text="Describe the record or explicit assumption behind these values. Leave blank when the source is unknown.",
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
            ("observed", "Observed in a record"),
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
        from farmcredit.interfaces.web.intake_guidance import FIELD_HELP

        for name, help_text in FIELD_HELP.items():
            self.fields[name].help_text = help_text
        for field in self.fields.values():
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.update(inputmode="decimal", step="0.01")
        self.fields[
            "schedule"
        ].help_text += " Example: payment-1, 2027-09-30, 22000.00. This means KSh 22,000 due on 30 September 2027."
        self.fields[
            "cash_records"
        ].help_text += (
            " Example: food-1, 2027-07-01, -3000.00. This means KSh 3,000 spent on 1 July 2027."
        )
        # Display neutral wording without changing unchanged saved evidence on POST.
        from farmcredit.interfaces.web.presentation import display_text

        self.initial = dict(self.initial)
        self._original_text = {}
        for name, field in self.fields.items():
            if isinstance(field, forms.CharField) and not isinstance(field, forms.ChoiceField):
                original = self.initial.get(name)
                if isinstance(original, str):
                    self._original_text[name] = original
                    self.initial[name] = display_text(original)
        self.order_fields(
            [
                "farmer",
                "cooperative_name",
                "production_pattern",
                "kamis_county",
                "kamis_classification",
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
        if "production_pattern" not in self.data:
            data["production_pattern"] = "single_harvest"
        from farmcredit.interfaces.web.presentation import display_text

        for name, original in self._original_text.items():
            if data.get(name) == display_text(original):
                data[name] = original
        if data.get("recorded_on") and data["recorded_on"] > timezone.localdate():
            self.add_error("recorded_on", "The source recording date cannot be in the future.")
        if not self.errors:
            try:
                self.inputs = intake_inputs(data)
            except ValueError as error:
                self.add_error(None, str(error))
        return data
