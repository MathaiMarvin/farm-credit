# SPDX-License-Identifier: AGPL-3.0-only
"""PostgreSQL persistence using Django transactions and per-case row locks."""

import json

from django.db import transaction
from django.db.models import Max

from farmcredit.adapters.persistence.models import Assessment, CaseState, Review
from farmcredit.application.saved_assessments import POLICY_VERSION, SavedAssessment
from farmcredit.domain.review import AdvisoryReview, ReviewRequest, validate_review


def _saved(row: Assessment) -> SavedAssessment:
    return SavedAssessment(
        row.pk, row.case_id, row.version, row.saved_at.isoformat(), row.snapshot_json
    )


def _review(row: Review) -> AdvisoryReview:
    return AdvisoryReview(
        row.pk,
        row.assessment_id,
        row.case_revision,
        row.decision,
        row.note,
        str(row.officer_id),
        row.officer_name,
        row.reviewed_at.isoformat(),
    )


def _locked_case(case_id: str) -> CaseState:
    CaseState.objects.get_or_create(case_id=case_id)
    return CaseState.objects.select_for_update().get(pk=case_id)


class AssessmentStore:
    @transaction.atomic
    def save(self, snapshot_json: str, operation_id: str) -> SavedAssessment:
        case_id = json.loads(snapshot_json)["case_id"]
        _locked_case(case_id)
        version = (
            Assessment.objects.filter(case_id=case_id).aggregate(latest=Max("version"))["latest"]
            or 0
        ) + 1
        row, _ = Assessment.objects.get_or_create(
            assessment_id=operation_id,
            defaults={"case_id": case_id, "version": version, "snapshot_json": snapshot_json},
        )
        if row.snapshot_json != snapshot_json:
            raise ValueError("This save identifier already belongs to a different snapshot.")
        return _saved(row)

    def get(self, assessment_id: str) -> SavedAssessment | None:
        row = Assessment.objects.filter(pk=assessment_id).first()
        return _saved(row) if row else None

    def history(self, case_id: str) -> tuple[SavedAssessment, ...]:
        return tuple(_saved(row) for row in Assessment.objects.filter(case_id=case_id))

    @transaction.atomic
    def record_current_inputs(self, case_id: str, fingerprint: str | None) -> int:
        state = _locked_case(case_id)
        if state.fingerprint != fingerprint or state.revision == 0:
            state.fingerprint = fingerprint
            state.revision += 1
            state.save(update_fields=["fingerprint", "revision"])
        return state.revision

    @transaction.atomic
    def review_context(self, assessment_id: str) -> dict:
        assessment = Assessment.objects.filter(pk=assessment_id).first()
        if assessment is None:
            raise ValueError("Saved assessment not found.")
        state = _locked_case(assessment.case_id)
        review = Review.objects.filter(assessment_id=assessment_id).first()
        snapshot = json.loads(assessment.snapshot_json)
        current = (
            Assessment.objects.filter(case_id=assessment.case_id).first().pk == assessment_id
            and state.fingerprint == snapshot["input_fingerprint"]
            and snapshot.get("inputs", {}).get("policy_version") == POLICY_VERSION
        )
        return {
            "revision": state.revision,
            "current": current,
            "review": _review(review) if review else None,
            "review_current": bool(review) and current and review.case_revision == state.revision,
        }

    @transaction.atomic
    def review(self, request: ReviewRequest) -> AdvisoryReview:
        assessment = Assessment.objects.filter(pk=request.assessment_id).first()
        if assessment is None:
            raise ValueError("Saved assessment not found.")
        state = _locked_case(assessment.case_id)
        prior = Review.objects.filter(pk=request.operation_id).first()
        if prior:
            if (prior.assessment_id, prior.decision, prior.note, str(prior.officer_id)) != (
                request.assessment_id,
                request.decision,
                request.note,
                request.officer.user_id,
            ):
                raise ValueError("Conflicting review retry.")
            if not request.officer.may_review or not request.officer.name.strip():
                raise ValueError("A named, authorised officer must review the advisory.")
            return _review(prior)
        snapshot = json.loads(assessment.snapshot_json)
        latest = Assessment.objects.filter(case_id=assessment.case_id).first()
        validate_review(
            request,
            latest=assessment.pk == latest.pk
            and snapshot.get("inputs", {}).get("policy_version") == POLICY_VERSION,
            saved_fingerprint=snapshot["input_fingerprint"],
            current_fingerprint=state.fingerprint,
            current_revision=state.revision,
            already_reviewed=Review.objects.filter(assessment_id=assessment.pk).exists(),
        )
        row = Review.objects.create(
            operation_id=request.operation_id,
            assessment=assessment,
            case_revision=state.revision,
            decision=request.decision,
            note=request.note,
            officer_id=request.officer.user_id,
            officer_name=request.officer.name,
        )
        return _review(row)
