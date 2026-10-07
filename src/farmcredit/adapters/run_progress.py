# SPDX-License-Identifier: AGPL-3.0-only
"""Read committed run activity without waiting on the execution transaction's lock."""

import json

from django.utils import timezone

from farmcredit.adapters.case_reader import _require_officer
from farmcredit.adapters.persistence.models import AgentRun
from farmcredit.application.run_tools import MAX_RUN_SECONDS


def read_run_progress(run_id, officer_id):
    _require_officer(officer_id)
    run = AgentRun.objects.filter(pk=run_id, officer_id=officer_id).first()
    if run is None:
        return None
    latest = run.events.order_by("-pk").first()
    detail = json.loads(latest.payload_json) if latest else {}
    return {
        "run_id": str(run.pk),
        "status": run.status,
        "started_at": run.started_at.isoformat(),
        "elapsed_seconds": int(
            ((run.finished_at or timezone.now()) - run.started_at).total_seconds()
        ),
        "reason": run.reason,
        "draft_id": run.draft_id,
        "application_id": str(run.application_id),
        "timed_out": run.status == "active"
        and (timezone.now() - run.started_at).total_seconds() >= MAX_RUN_SECONDS + 5,
        "calls": [
            {
                "tool": call.tool,
                "status": call.status,
                "error": call.error,
                "arguments": json.loads(call.arguments_json),
                "result": json.loads(call.result_json) if call.result_json else None,
            }
            for call in run.calls.all()
        ],
        "last_event": latest.kind if latest else None,
        "event_detail": {
            key: detail[key]
            for key in ("attempt", "timeout_seconds", "error", "retry_scheduled", "retry_after")
            if key in detail
        },
        "model_requests": run.events.filter(kind="model_request").count(),
        "model_responses": run.events.filter(kind="model_response").count(),
    }
