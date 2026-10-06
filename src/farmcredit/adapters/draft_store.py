# SPDX-License-Identifier: AGPL-3.0-only
"""Atomic, append-only advisory persistence for an authenticated case binding."""

from django.db import transaction
from django.db.models import Max

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.adapters.case_reader import BoundCaseReader
from farmcredit.adapters.persistence.models import Assessment, CaseState, Draft
from farmcredit.application.assess_saved_case import assess_cashflow
from farmcredit.application.get_case import get_case
from farmcredit.application.save_draft import DraftRequest, SavedDraft, prepare_draft
from farmcredit.application.saved_assessments import POLICY_VERSION, canonical_json


def _saved(row: Draft) -> SavedDraft:
    return SavedDraft(
        row.pk, row.assessment_id, row.version, row.saved_at.isoformat(), row.snapshot_json
    )


@transaction.atomic
def save_draft(reader: BoundCaseReader, request: DraftRequest) -> SavedDraft:
    """Trusted reader comes from the authenticated session, never model arguments.

    Exact retries return the original draft even if it has since become stale.
    They never create a new draft or confer approval.
    """
    reader._require_access()
    scope = reader.scope
    state = CaseState.objects.select_for_update().get(pk=scope.case_id)
    request_json = canonical_json({"scope": scope, "request": request})
    prior = Draft.objects.filter(pk=request.operation_id).first()
    if prior:
        if prior.request_json != request_json or str(prior.officer_id) != scope.officer_id:
            raise ValueError("Conflicting draft retry.")
        return _saved(prior)
    saved = AssessmentStore().get(scope.assessment_id)
    brief = get_case(scope, lambda key: saved)
    latest = Assessment.objects.filter(case_id=scope.case_id).first()
    if (
        latest.pk != scope.assessment_id
        or state.fingerprint != brief.input_fingerprint
        or brief.policy_version != POLICY_VERSION
    ):
        raise ValueError("Inputs have changed; use the current saved assessment before drafting.")
    calculation = assess_cashflow(scope, lambda key: saved, request.assumptions)
    snapshot = prepare_draft(request, brief, calculation)
    version = (
        Draft.objects.filter(assessment_id=scope.assessment_id).aggregate(latest=Max("version"))[
            "latest"
        ]
        or 0
    ) + 1
    row = Draft.objects.create(
        operation_id=request.operation_id,
        assessment_id=scope.assessment_id,
        officer_id=scope.officer_id,
        case_revision=state.revision,
        version=version,
        request_json=request_json,
        snapshot_json=snapshot,
    )
    return _saved(row)
