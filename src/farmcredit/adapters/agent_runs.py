# SPDX-License-Identifier: AGPL-3.0-only
"""Durable, bounded execution of internal tools for one officer and saved version."""

import json
from dataclasses import replace
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from farmcredit.adapters.case_reader import (
    BoundCaseReader,
    _require_officer,
    bind_application_reader,
    bind_case_reader,
)
from farmcredit.adapters.draft_store import save_draft
from farmcredit.adapters.market_hdx import snapshot_market
from farmcredit.adapters.market_kamis import snapshot_kamis
from farmcredit.adapters.persistence.models import (
    AgentRun,
    ApplicationVersion,
    Assessment,
    CaseState,
    InvestigationEvent,
    RunEvidence,
    ToolCall,
)
from farmcredit.adapters.weather_mcp import snapshot_weather
from farmcredit.application.get_case import CaseScope
from farmcredit.application.run_tools import (
    MAX_RUN_SECONDS,
    MAX_TOOL_CALLS,
    ToolName,
    draft_request,
    stress_assumptions,
    validate_arguments,
)
from farmcredit.application.saved_assessments import (
    POLICY_VERSION,
    canonical_json,
    input_fingerprint,
)


def _reader(run: AgentRun) -> BoundCaseReader:
    scope = json.loads(run.scope_json)
    scope["evidence_as_of"] = date.fromisoformat(scope["evidence_as_of"])
    for evidence in run.evidence.all():
        scope[EXTERNAL_EVIDENCE[evidence.category][0]] = evidence.snapshot_json
    return BoundCaseReader(CaseScope(**scope))


def _owned_run(run_id: str, officer_id: str) -> AgentRun:
    _require_officer(officer_id)
    run = (
        AgentRun.objects.select_for_update(of=("self",))
        .filter(pk=run_id, officer_id=officer_id)
        .first()
    )
    if run is None:
        raise LookupError("Run not found for this officer.")
    return run


def _current(run: AgentRun, reader: BoundCaseReader) -> None:
    state = CaseState.objects.select_for_update().get(pk=reader.scope.case_id)
    brief = reader.get_case()
    reader.require_current_policy()
    if run.application_id:
        latest = ApplicationVersion.objects.filter(case_id=state.pk).first()
        current_binding = latest is not None and str(latest.pk) == str(run.application_id)
    else:
        latest = Assessment.objects.filter(case_id=state.pk).first()
        current_binding = latest is not None and latest.pk == run.assessment_id
    if (
        state.revision != run.case_revision
        or state.fingerprint != brief.input_fingerprint
        or not current_binding
        or brief.policy_version != POLICY_VERSION
    ):
        raise ValueError("The case changed. Start a new run from the current saved version.")


def _expired(run: AgentRun) -> bool:
    return (timezone.now() - run.started_at).total_seconds() >= MAX_RUN_SECONDS


def _stop(run: AgentRun, reason: str) -> None:
    run.status, run.reason, run.finished_at = "incomplete", reason, timezone.now()
    run.save(update_fields=["status", "reason", "finished_at"])


@transaction.atomic
def start_run(
    *,
    officer_id: str,
    assessment_id: str | None = None,
    application_id: str | None = None,
    model: str = "",
    run_id: str | None = None,
    request_context: dict | None = None,
) -> str:
    if bool(assessment_id) == bool(application_id):
        raise ValueError("Select exactly one application or historical assessment.")
    reader = (
        bind_application_reader(officer_id=officer_id, application_id=application_id)
        if application_id
        else bind_case_reader(officer_id=officer_id, assessment_id=assessment_id)
    )
    if application_id and not model:
        inputs = reader.read_saved(application_id).snapshot["inputs"]
        reader = BoundCaseReader(
            replace(
                reader.scope,
                weather_snapshot_json=snapshot_weather(
                    inputs["context"]["weather_reference"],
                    as_of=reader.scope.evidence_as_of,
                    retrieved_at=timezone.now(),
                )
                if inputs.get("context", {}).get("weather_reference")
                else None,
                kamis_snapshot_json=snapshot_kamis(
                    inputs["context"]["kamis_market_reference"],
                    as_of=reader.scope.evidence_as_of,
                    retrieved_at=timezone.now(),
                )
                if inputs.get("context", {}).get("kamis_market_reference")
                else None,
                market_snapshot_json=snapshot_market(
                    inputs.get("context", {}).get("market_reference"),
                    as_of=reader.scope.evidence_as_of,
                    retrieved_at=timezone.now(),
                ),
            )
        )
    state = CaseState.objects.select_for_update().get(pk=reader.scope.case_id)
    run = AgentRun(
        run_id=UUID(run_id) if run_id else uuid4(),
        execution_kind="model" if model else "internal_tools",
        model=model,
        officer_id=officer_id,
        assessment_id=assessment_id,
        application_id=application_id,
        scope_json=canonical_json(reader.scope),
        case_revision=state.revision,
    )
    _current(run, reader)
    run.save(force_insert=True)
    if request_context is not None:
        record_event(str(run.pk), "officer_request", request_context)
    return str(run.pk)


def _outcome(call: ToolCall) -> dict:
    return {
        "operation_id": str(call.operation_id),
        "sequence": call.sequence,
        "tool": call.tool,
        "status": call.status,
        "result": json.loads(call.result_json) if call.result_json is not None else None,
        "error": call.error or None,
        "started_at": call.started_at.isoformat(),
        "finished_at": call.finished_at.isoformat() if call.finished_at else None,
    }


@transaction.atomic
def _claim(run_id, officer_id, operation_id, tool, arguments_json):
    run = _owned_run(run_id, officer_id)
    prior = run.calls.filter(operation_id=operation_id).first()
    if prior:
        if prior.tool != tool.value or prior.arguments_json != arguments_json:
            raise ValueError("Conflicting tool-call retry.")
        return prior, False, None
    if run.status != "active":
        return None, False, "This run has ended."
    if _expired(run) or run.calls.count() >= MAX_TOOL_CALLS:
        reason = "Run deadline exceeded." if _expired(run) else "Tool-call limit reached."
        _stop(run, reason)
        return None, False, reason
    if run.calls.filter(status="running").exists():
        raise ValueError("A tool call is already in progress; inspect its recorded outcome.")
    call = ToolCall.objects.create(
        run=run,
        operation_id=operation_id,
        sequence=run.calls.count() + 1,
        tool=tool.value,
        arguments_json=arguments_json,
    )
    return call, True, None


@transaction.atomic
def _execute(run_id, officer_id, call_id):
    run = _owned_run(run_id, officer_id)
    call = ToolCall.objects.get(pk=call_id)
    if run.status != "active" or _expired(run):
        raise ValueError("Run deadline exceeded or run ended.")
    reader = _reader(run)
    _current(run, reader)
    tool, arguments = ToolName(call.tool), json.loads(call.arguments_json)
    validate_arguments(tool, arguments)
    if tool == ToolName.GET_CASE:
        result = reader.get_case()
    elif tool == ToolName.GET_RECORDS:
        # Validate before making any external request.
        reader.get_records(arguments["categories"])
        if run.execution_kind == "model":
            retrieve_evidence(run, reader, arguments["categories"])
            reader = _reader(run)
        result = reader.get_records(arguments["categories"])
    elif tool == ToolName.ASSESS_CASHFLOW:
        result = reader.assess_cashflow(stress_assumptions(arguments))
    else:
        request = draft_request(
            arguments,
            input_fingerprint({"run_id": str(run.pk), "operation_id": str(call.operation_id)}),
        )
        # The model can reference only a calculation actually returned in this run.
        calculations = [
            json.loads(item.result_json)
            for item in run.calls.filter(tool=ToolName.ASSESS_CASHFLOW.value, status="succeeded")
        ]
        expected_assumptions = json.loads(canonical_json(request.assumptions))
        institution = reader.get_institution()
        has_gaps = reader.get_case().gaps or (
            institution and institution.review.status != "checks_satisfied"
        )
        if not any(
            item["assumptions"] == expected_assumptions
            and (
                item["calculation_id"] == request.calculation_id
                or (request.calculation_id is None and item["comparison"] is None)
            )
            for item in calculations
        ) and not (
            run.application_id
            and request.calculation_id is None
            and has_gaps
            and request.questions
            and not request.statements
        ):
            raise ValueError("Draft needs a matching calculation from this run.")
        result = save_draft(reader, request)
        run.draft_id = result.draft_id
    if _expired(run):
        # Roll back a late draft and its success event together.
        raise ValueError("Run deadline exceeded during tool execution.")
    call.status, call.result_json, call.finished_at = (
        "succeeded",
        canonical_json(result),
        timezone.now(),
    )
    call.save(update_fields=["status", "result_json", "finished_at"])
    if tool == ToolName.SAVE_DRAFT:
        run.status, run.finished_at = "completed", timezone.now()
        run.save(update_fields=["draft", "status", "finished_at"])
    return _outcome(call)


@transaction.atomic
def _failed(run_id, call_id, error):
    run = AgentRun.objects.select_for_update().get(pk=run_id)
    call = ToolCall.objects.get(pk=call_id)
    call.status, call.error, call.finished_at = "failed", error[:256], timezone.now()
    call.save(update_fields=["status", "error", "finished_at"])
    if run.status == "active":
        _stop(run, "Tool execution failed.")
    return _outcome(call)


def invoke_tool(
    *, run_id: str, officer_id: str, operation_id: str, tool: str, arguments: dict
) -> dict:
    """Session supplies officer/run; the future model supplies only tool arguments.

    A durable running record precedes execution. A crash or database outage leaves
    that state observable, never an invented success. Calls are serial per run.
    """
    name, operation = ToolName(tool), UUID(operation_id)
    payload = canonical_json(arguments)
    if len(payload.encode()) > 65536:
        raise ValueError("Tool arguments exceed the supported size.")
    call, execute, error = _claim(run_id, officer_id, operation, name, payload)
    if error:
        raise ValueError(error)
    if not execute:
        return _outcome(call)
    try:
        return _execute(run_id, officer_id, call.pk)
    except Exception as exception:
        # Do not expose database credentials, provider responses or tracebacks.
        reason = (
            str(exception)
            if isinstance(exception, (ValueError, PermissionError, LookupError))
            else "Tool failed; no result was confirmed."
        )
        return _failed(run_id, call.pk, reason)


@transaction.atomic
def run_details(*, run_id: str, officer_id: str) -> dict:
    run = _owned_run(run_id, officer_id)
    if run.status == "active" and _expired(run):
        _stop(run, "Run deadline exceeded.")
    return {
        "run_id": str(run.pk),
        "assessment_id": run.assessment_id,
        "application_id": str(run.application_id) if run.application_id else None,
        "status": run.status,
        "execution_kind": run.execution_kind,
        "model": run.model or None,
        "events": [
            {
                "kind": event.kind,
                "recorded_at": event.recorded_at.isoformat(),
                "payload": json.loads(event.payload_json),
            }
            for event in run.events.all()
        ],
        **model_usage(run),
        "reason": run.reason or None,
        "draft_id": run.draft_id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "calls": [
            {**_outcome(call), "arguments": json.loads(call.arguments_json)}
            for call in run.calls.all()
        ],
    }


EXTERNAL_EVIDENCE = {
    "market_prices": ("market_snapshot_json", "market_reference", snapshot_market),
    "kamis_prices": ("kamis_snapshot_json", "kamis_market_reference", snapshot_kamis),
    "weather": ("weather_snapshot_json", "weather_reference", snapshot_weather),
}


def record_event(run_id, kind, payload):
    return InvestigationEvent.objects.create(
        run_id=run_id, kind=kind, payload_json=canonical_json(payload)
    )


def retrieve_evidence(run, reader, categories):
    inputs = reader.read_saved(reader.scope.input_id).snapshot["inputs"]
    for category in categories:
        if category not in EXTERNAL_EVIDENCE or run.evidence.filter(category=category).exists():
            continue
        field, reference, fetch = EXTERNAL_EVIDENCE[category]
        selected = inputs.get("context", {}).get(reference)
        if not selected:
            continue
        started = timezone.now()
        snapshot = fetch(selected, as_of=reader.scope.evidence_as_of, retrieved_at=started)
        RunEvidence.objects.create(run=run, category=category, snapshot_json=snapshot)
        record_event(
            run.pk,
            "external_evidence",
            {
                "category": category,
                "started_at": started.isoformat(),
                "finished_at": timezone.now().isoformat(),
                "snapshot": json.loads(snapshot),
                "usage": None,
                "cost": None,
            },
        )


@transaction.atomic
def stop_run(run_id, officer_id, reason):
    run = _owned_run(run_id, officer_id)
    if run.status == "active":
        _stop(run, reason)


def model_usage(run):
    outcomes = list(run.events.filter(kind__in=["model_response", "model_failure"]))
    requests = run.events.filter(kind="model_request").count()
    usages = [json.loads(event.payload_json).get("usage") for event in outcomes]
    complete = bool(requests) and requests == len(outcomes)
    tokens = []
    costs = []
    for usage in usages:
        usage = usage if isinstance(usage, dict) else {}
        value = usage.get("total_tokens")
        if type(value) is int and value >= 0:
            tokens.append(value)
        try:
            cost = Decimal(str(usage.get("cost")))
            if cost.is_finite() and cost >= 0:
                costs.append(cost)
        except InvalidOperation:
            pass
    return {
        "token_usage": sum(tokens) if complete and len(tokens) == requests else None,
        "cost": str(sum(costs)) if complete and len(costs) == requests else None,
        "model_attempts": requests,
    }
