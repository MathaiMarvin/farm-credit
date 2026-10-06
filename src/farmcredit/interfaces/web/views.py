# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace
from datetime import date
from uuid import uuid4

from django.core import signing
from django.db import DatabaseError
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.adapters.demo import (
    load_demo_case,
    load_demo_evidence,
    load_monthly_case,
    load_monthly_evidence,
)
from farmcredit.application.saved_assessments import (
    SCHEMA_VERSION,
    canonical_json,
    input_fingerprint,
    input_snapshot,
    make_snapshot,
)
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress
from farmcredit.domain.evidence import EvidenceBasis, EvidenceRecord, InputValue
from farmcredit.interfaces.web.forms import ScenarioForm


def _input_label(field: str) -> str:
    labels = {
        "coverage_through": "Household cash-flow coverage confirmed through",
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
        .removeprefix("repayment/")
        .replace("/on", " / date")
        .replace("/amount", " / amount")
        .replace("-", " ")
        .capitalize(),
    )


def _apply_scenario(case, evidence, cleaned_data, previous_records=()):
    previous_by_id = {record["record_id"]: record for record in previous_records}
    case = replace(
        case,
        sale=replace(
            case.sale,
            received_on=cleaned_data["received_on"],
            price_per_kg=cleaned_data["price_per_kg"],
        ),
    )
    records = []
    for record in evidence:
        field = record.input.field.removeprefix("sale.")
        if record.input.field.startswith("sale.") and field in cleaned_data:
            current = InputValue(record.input.field, cleaned_data[field], record.input.unit)
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
        previous = previous_by_id.get(record.record_id)
        if previous and record.record_id.startswith("scenario:"):
            candidate = replace(record, recorded_on=date.fromisoformat(previous["recorded_on"]))
            if canonical_json(candidate) == canonical_json(previous):
                record = candidate
        records.append(record)
    evidence = tuple(records)
    return case, evidence


@never_cache
@require_http_methods(["GET", "POST"])
def workspace(request):
    mode = (request.POST if request.method == "POST" else request.GET).get(
        "repayment_mode", "seasonal"
    )
    if mode not in ("seasonal", "monthly"):
        return HttpResponseBadRequest("Unsupported repayment demonstration.")
    reference_id = (request.POST if request.method == "POST" else request.GET).get("reference")
    try:
        reference = AssessmentStore().get(reference_id) if reference_id else None
    except DatabaseError:
        return render(
            request,
            "farmcredit/saved_assessments.html",
            {"storage_error": "The saved version is temporarily unavailable. Try again."},
            status=503,
        )
    if reference and reference.snapshot["schema_version"] != SCHEMA_VERSION:
        return HttpResponseBadRequest(
            "This saved version requires a compatible application version."
        )
    if reference_id and reference is None:
        raise Http404("Saved assessment not found.")
    if reference and request.method == "GET":
        mode = reference.snapshot["inputs"]["repayment_mode"]
    monthly = mode == "monthly"
    case = load_monthly_case() if monthly else load_demo_case()
    initial = {"received_on": case.sale.received_on, "price_per_kg": case.sale.price_per_kg}
    if reference:
        previous = reference.snapshot["inputs"]
        initial = {
            "received_on": previous["case"]["sale"]["received_on"],
            "price_per_kg": previous["case"]["sale"]["price_per_kg"],
            **previous["assumptions"],
        }
    form = ScenarioForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
    )
    save_token = None
    reference_status = "Calculate to compare with this saved version."
    result = None
    stress_scenarios = ()
    evidence = load_monthly_evidence() if monthly else load_demo_evidence()
    evidence_issues = ()
    if request.method == "POST" and form.is_valid():
        case, evidence = _apply_scenario(
            case,
            evidence,
            form.cleaned_data,
            reference.snapshot["inputs"]["evidence"] if reference else (),
        )
        try:
            assumptions = StressAssumptions(
                form.cleaned_data["price_reduction"], form.cleaned_data["harvest_reduction"]
            )
            inputs = input_snapshot(case, evidence, assumptions, mode)
            AssessmentStore().record_current_inputs("FC-001", input_fingerprint(inputs))
            if reference:
                reference_status = (
                    "Stale for these inputs: the saved version has different inputs, sources or policy."
                    if input_fingerprint(inputs) != reference.snapshot["input_fingerprint"]
                    else "Current inputs, sources and policy match this saved version."
                )
            comparison = compare_stress(
                case,
                evidence,
                assumptions,
                as_of=timezone.localdate(),
            )
            assessment = comparison.baseline
            stress_scenarios = comparison.scenarios
            result = assessment.cashflow
            evidence_issues = assessment.issues
            if result is not None:
                save_token = signing.dumps(
                    {
                        "operation_id": str(uuid4()),
                        "snapshot_json": make_snapshot(inputs, comparison),
                    },
                    salt="assessment-save",
                    compress=True,
                )
        except ValueError as error:
            form.add_error(None, str(error))
        except DatabaseError:
            form.add_error(None, "Current case state could not be saved. Try calculating again.")
    elif request.method == "POST":
        try:
            AssessmentStore().record_current_inputs("FC-001", None)
        except DatabaseError:
            form.add_error(None, "Current case state could not be saved. Try again.")
    context = {
        "case": case,
        "save_token": save_token,
        "reference": reference,
        "reference_status": reference_status,
        "repayment_mode": mode,
        "monthly": monthly,
        "schedule_rows": [
            {"on": item.on, "due": -item.amount} for item in case.financing.as_repayments()
        ],
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
