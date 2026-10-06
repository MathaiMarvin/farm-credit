# SPDX-License-Identifier: AGPL-3.0-only
"""Validate advisory content against server-resolved evidence and calculations."""

from dataclasses import dataclass

from farmcredit.application.assess_saved_case import Calculation
from farmcredit.application.get_case import CaseBrief
from farmcredit.application.saved_assessments import canonical_json
from farmcredit.application.stress_scenarios import StressAssumptions


@dataclass(frozen=True)
class CitedStatement:
    text: str
    record_ids: tuple[str, ...]


@dataclass(frozen=True)
class DraftRequest:
    operation_id: str
    calculation_id: str | None
    assumptions: StressAssumptions
    statements: tuple[CitedStatement, ...]
    questions: tuple[str, ...]

    def __post_init__(self):
        if (
            not isinstance(self.operation_id, str)
            or not 1 <= len(self.operation_id) <= 64
            or self.operation_id.strip() != self.operation_id
        ):
            raise ValueError("A nonblank retry identifier of at most 64 characters is required.")
        if not isinstance(self.assumptions, StressAssumptions):
            raise ValueError("Explicit stress assumptions are required.")
        if not isinstance(self.statements, tuple) or not isinstance(self.questions, tuple):
            raise ValueError("Draft content must be immutable tuples.")
        if not self.statements and not self.questions:
            raise ValueError("A draft needs cited statements or questions.")
        if len(self.statements) > 30 or len(self.questions) > 30:
            raise ValueError("A draft supports at most 30 statements and 30 questions.")
        for statement in self.statements:
            if (
                not isinstance(statement, CitedStatement)
                or not isinstance(statement.record_ids, tuple)
                or not statement.record_ids
            ):
                raise ValueError("Each statement needs evidence citations.")
            _text(statement.text)
            if any(not isinstance(key, str) for key in statement.record_ids) or len(
                set(statement.record_ids)
            ) != len(statement.record_ids):
                raise ValueError("Citations must be distinct record identifiers.")
        for question in self.questions:
            _text(question)


def _text(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or len(value) > 2000:
        raise ValueError("Draft text must contain 1–2000 characters.")


@dataclass(frozen=True)
class SavedDraft:
    draft_id: str
    assessment_id: str
    version: int
    saved_at: str
    snapshot_json: str


def prepare_draft(request: DraftRequest, brief: CaseBrief, calculation: Calculation) -> str:
    if (calculation.assessment_id, calculation.case_id, calculation.version) != (
        brief.assessment_id,
        brief.case_id,
        brief.version,
    ):
        raise ValueError("Calculation does not belong to the bound assessment.")
    if calculation.assumptions != request.assumptions:
        raise ValueError("Calculation assumptions do not match the draft.")
    if request.calculation_id != calculation.calculation_id:
        if request.calculation_id is not None or calculation.comparison is not None:
            raise ValueError("Calculation reference does not match the server result.")
    available = {record.record_id for record in brief.sources}
    if any(not set(statement.record_ids) <= available for statement in request.statements):
        raise ValueError("A citation does not belong to this saved case version.")
    incomplete = (
        calculation.comparison is None or bool(calculation.issues) or bool(calculation.error)
    )
    if incomplete and not request.questions:
        raise ValueError("An incomplete assessment needs questions for the officer.")
    return canonical_json(
        {
            "status": "draft",
            "kind": "evidence_request" if incomplete else "advisory",
            "assessment_id": brief.assessment_id,
            "case_id": brief.case_id,
            "input_version": brief.version,
            "input_fingerprint": brief.input_fingerprint,
            "statements": request.statements,
            "questions": request.questions,
            "sources": brief.sources,
            "calculation": calculation,
            "limitations": (
                *brief.limitations,
                "Citation membership is checked; factual support for narrative claims requires officer review. This draft is not approved.",
            ),
        }
    )
