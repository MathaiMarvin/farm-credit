# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace

from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from farmcredit.adapters.demo import load_demo_case, load_demo_evidence
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress
from farmcredit.domain.evidence import EvidenceBasis, EvidenceRecord, InputValue
from farmcredit.interfaces.web.forms import ScenarioForm


def _input_label(field: str) -> str:
    labels = {
        "starts_on": "Assessment start date",
        "opening_cash": "Opening available cash",
        "sale.harvest_on": "Expected harvest date",
        "sale.received_on": "Expected sale receipt date",
        "sale.gross_kg": "Expected harvest quantity",
        "sale.retained_kg": "Harvest retained by household",
        "sale.lost_kg": "Expected harvest loss",
        "sale.price_per_kg": "Assumed sale price",
        "financing.supplied_on": "Input supply date",
        "financing.principal": "Financed input amount",
        "financing.charges": "Financing charges",
        "financing.repayment_on": "Proposed repayment date",
    }
    return labels.get(
        field,
        field.removeprefix("cash/")
        .replace("/on", " / date")
        .replace("/amount", " / amount")
        .replace("-", " ")
        .capitalize(),
    )


@never_cache
@require_http_methods(["GET", "POST"])
def workspace(request):
    case = load_demo_case()
    form = ScenarioForm(
        request.POST if request.method == "POST" else None,
        initial={
            "received_on": case.sale.received_on,
            "price_per_kg": case.sale.price_per_kg,
        },
    )
    result = None
    stress_scenarios = ()
    evidence = load_demo_evidence()
    evidence_issues = ()
    if request.method == "POST" and form.is_valid():
        case = replace(
            case,
            sale=replace(
                case.sale,
                received_on=form.cleaned_data["received_on"],
                price_per_kg=form.cleaned_data["price_per_kg"],
            ),
        )
        records = []
        for record in evidence:
            field = record.input.field.removeprefix("sale.")
            if record.input.field.startswith("sale.") and field in form.cleaned_data:
                current = InputValue(
                    record.input.field, form.cleaned_data[field], record.input.unit
                )
                if current != record.input:
                    record = EvidenceRecord(
                        record_id=f"scenario:{record.input.field}",
                        input=current,
                        source=f"Unsaved scenario edit; replaces {record.record_id} "
                        f"({record.input.value} {record.input.unit})",
                        recorded_on=timezone.localdate(),
                        basis=EvidenceBasis.ASSUMED,
                        synthetic=True,
                    )
            records.append(record)
        evidence = tuple(records)
        try:
            comparison = compare_stress(
                case,
                evidence,
                StressAssumptions(
                    form.cleaned_data["price_reduction"], form.cleaned_data["harvest_reduction"]
                ),
                as_of=timezone.localdate(),
            )
            assessment = comparison.baseline
            stress_scenarios = comparison.scenarios
            result = assessment.cashflow
            evidence_issues = assessment.issues
        except ValueError as error:
            form.add_error(None, str(error))
    context = {
        "case": case,
        "evidence_records": evidence,
        "evidence_rows": [
            {"label": _input_label(record.input.field), "record": record} for record in evidence
        ],
        "evidence_issues": [
            {
                "field": _input_label(issue.field),
                "reason": issue.reason,
                "record_ids": issue.record_ids,
            }
            for issue in evidence_issues
        ],
        "form": form,
        "result": result,
        "stress_scenarios": stress_scenarios,
        "cash_records": sorted(case.other_movements, key=lambda movement: movement.on),
        "repayment_amount": -case.financing.as_repayment().amount,
        "shortfall_amount": -result.cash_after_repayment
        if result and result.cash_after_repayment < 0
        else None,
    }
    template = "farmcredit/workspace.html"
    if request.headers.get("HX-Request") == "true":
        template = "farmcredit/calculation.html"
    return render(request, template, context)
