# SPDX-License-Identifier: AGPL-3.0-only
"""Durable, bounded execution of internal tools for one officer and saved version."""

import json
from datetime import date
from uuid import UUID, uuid4

from django.db import transaction
from django.utils import timezone

from farmcredit.adapters.case_reader import (
    DEMO_CASE_ID,
    BoundCaseReader,
    _require_officer,
    bind_case_reader,
)
from farmcredit.adapters.draft_store import save_draft
from farmcredit.adapters.persistence.models import AgentRun, Assessment, CaseState, ToolCall
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
    return BoundCaseReader(CaseScope(**scope))


def _owned_run(run_id: str, officer_id: str) -> AgentRun:
    _require_officer(officer_id)
    run = (
        AgentRun.objects.select_for_update(of=("self",))
        .filter(pk=run_id, officer_id=officer_id, assessment__case_id=DEMO_CASE_ID)
        .first()
    )
    if run is None:
        raise LookupError("Run not found for this officer.")
    return run


def _current(run: AgentRun, reader: BoundCaseReader) -> None:
    state = CaseState.objects.select_for_update().get(pk=reader.scope.case_id)
    brief = reader.get_case()
    latest = Assessment.objects.filter(case_id=state.pk).first()
    if (
        state.revision != run.case_revision
        or state.fingerprint != brief.input_fingerprint
        or latest.pk != run.assessment_id
        or brief.policy_version != POLICY_VERSION
    ):
        raise ValueError("The case changed. Start a new run from the current saved assessment.")


def _expired(run: AgentRun) -> bool:
    return (timezone.now() - run.started_at).total_seconds() >= MAX_RUN_SECONDS


def _stop(run: AgentRun, reason: str) -> None:
    run.status, run.reason, run.finished_at = "incomplete", reason, timezone.now()
    run.save(update_fields=["status", "reason", "finished_at"])


@transaction.atomic
def start_run(*, officer_id: str, assessment_id: str) -> str:
    reader = bind_case_reader(officer_id=officer_id, assessment_id=assessment_id)
    state = CaseState.objects.select_for_update().get(pk=reader.scope.case_id)
    run = AgentRun(
        run_id=uuid4(),
        officer_id=officer_id,
        assessment_id=assessment_id,
        scope_json=canonical_json(reader.scope),
        case_revision=state.revision,
    )
    _current(run, reader)
    run.save(force_insert=True)
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
        if not any(
            item["assumptions"] == expected_assumptions
            and (
                item["calculation_id"] == request.calculation_id
                or (request.calculation_id is None and item["comparison"] is None)
            )
            for item in calculations
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
        "status": run.status,
        "execution_kind": "internal_tools",
        "model": None,
        "token_usage": None,
        "cost": None,
        "reason": run.reason or None,
        "draft_id": run.draft_id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "calls": [
            {**_outcome(call), "arguments": json.loads(call.arguments_json)}
            for call in run.calls.all()
        ],
    }
