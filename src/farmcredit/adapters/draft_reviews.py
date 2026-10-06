# SPDX-License-Identifier: AGPL-3.0-only
"""Draft access and review share the same per-case lock as saves and input changes."""

import json
from dataclasses import replace

from django.db import transaction

from farmcredit.adapters.case_reader import DEMO_CASE_ID, _require_officer
from farmcredit.adapters.persistence.models import Assessment, CaseState, Draft, DraftReview
from farmcredit.application.saved_assessments import POLICY_VERSION
from farmcredit.domain.draft_review import DraftReviewRequest, validate_draft_review
from farmcredit.domain.review import Officer


def draft_history(assessment_id: str, officer_id: str):
    _require_officer(officer_id)
    return tuple(
        Draft.objects.filter(assessment_id=assessment_id, assessment__case_id=DEMO_CASE_ID)
        .select_related("review")
        .order_by("-version")
    )


def _locked_draft(draft_id: str):
    draft = (
        Draft.objects.select_related("assessment")
        .filter(pk=draft_id, assessment__case_id=DEMO_CASE_ID)
        .first()
    )
    if draft is None:
        raise LookupError("Draft not found.")
    state = CaseState.objects.select_for_update().get(pk=draft.assessment.case_id)
    snapshot = json.loads(draft.snapshot_json)
    latest_assessment = Assessment.objects.filter(case_id=state.pk).first()
    latest_draft = (
        Draft.objects.filter(assessment_id=draft.assessment_id).order_by("-version").first()
    )
    current = (
        latest_assessment.pk == draft.assessment_id
        and latest_draft.pk == draft.pk
        and state.fingerprint == snapshot["input_fingerprint"]
        and state.revision == draft.case_revision
        and snapshot["calculation"]["policy_version"] == POLICY_VERSION
    )
    return draft, state, snapshot, current


@transaction.atomic
def draft_context(draft_id: str, officer_id: str) -> dict:
    _require_officer(officer_id)
    draft, state, snapshot, current = _locked_draft(draft_id)
    review = DraftReview.objects.filter(draft_id=draft.pk).first()
    return {
        "draft": draft,
        "snapshot": snapshot,
        "review": review,
        "current": current,
        "revision": state.revision,
        "review_current": bool(review) and current and review.case_revision == state.revision,
    }


@transaction.atomic
def review_draft(request: DraftReviewRequest) -> DraftReview:
    # Resolve identity/permission afresh; caller-supplied names and flags are not trusted.
    user = _require_officer(request.officer.user_id)
    request = replace(request, officer=Officer(str(user.pk), user.get_full_name().strip(), True))
    draft, state, _, current = _locked_draft(request.draft_id)
    prior = DraftReview.objects.filter(pk=request.operation_id).first()
    if prior:
        if (
            prior.draft_id,
            str(prior.officer_id),
            prior.decision,
            prior.note,
            prior.case_revision,
        ) != (
            request.draft_id,
            request.officer.user_id,
            request.decision,
            request.note,
            request.expected_revision,
        ):
            raise ValueError("Conflicting draft review retry.")
        return prior
    validate_draft_review(
        request,
        current=current,
        revision=state.revision,
        already_reviewed=DraftReview.objects.filter(draft_id=draft.pk).exists(),
    )
    return DraftReview.objects.create(
        operation_id=request.operation_id,
        draft=draft,
        case_revision=state.revision,
        decision=request.decision,
        note=request.note,
        officer=user,
        officer_name=request.officer.name,
    )
