# SPDX-License-Identifier: AGPL-3.0-only
"""Officer-owned conversation context, read from immutable requests and drafts."""

import json

from django.db.models import Prefetch

from farmcredit.adapters.application_store import get_application
from farmcredit.adapters.persistence.models import AgentRun, InvestigationEvent
from farmcredit.application.investigation import DEFAULT_TASK


def conversation_runs(application_id: str, officer_id: str):
    get_application(application_id, officer_id)
    return (
        AgentRun.objects.filter(application_id=application_id, officer_id=officer_id)
        .select_related("draft")
        .prefetch_related(
            Prefetch(
                "events",
                queryset=InvestigationEvent.objects.filter(kind="officer_request"),
                to_attr="requests",
            )
        )
        .order_by("-started_at")
    )


def recorded_task(run):
    return json.loads(run.requests[0].payload_json)["task"] if run.requests else DEFAULT_TASK


def previous_response(application_id: str, officer_id: str):
    run = (
        conversation_runs(application_id, officer_id)
        .filter(status="completed", execution_kind="model", draft__isnull=False)
        .first()
    )
    if run is None:
        return None
    snapshot = json.loads(run.draft.snapshot_json)
    return {
        "run_id": str(run.pk),
        "draft_id": str(run.draft_id),
        "task": recorded_task(run),
        "statements": snapshot.get("statements", []),
        "questions": snapshot.get("questions", []),
    }
