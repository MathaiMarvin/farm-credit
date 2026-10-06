# SPDX-License-Identifier: AGPL-3.0-only
"""Retrieve categorised evidence from an authorised immutable case brief."""

from dataclasses import dataclass
from enum import Enum

from farmcredit.application.get_case import CaseBrief
from farmcredit.domain.evidence import EvidenceIssue, EvidenceRecord


class RecordCategory(str, Enum):
    CASH_FLOW = "cash_flow"
    HARVEST = "harvest"
    CREDIT_TERMS = "credit_terms"
    REPAYMENT_SCHEDULE = "repayment_schedule"
    REPAYMENT_HISTORY = "repayment_history"


class RecordStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class RecordGroup:
    category: RecordCategory
    status: RecordStatus
    records: tuple[EvidenceRecord, ...]
    gaps: tuple[EvidenceIssue, ...]
    explanation: str


@dataclass(frozen=True)
class CaseRecords:
    assessment_id: str
    case_id: str
    version: int
    groups: tuple[RecordGroup, ...]
    limitations: tuple[str, ...]


def _category(field: str) -> RecordCategory | None:
    if field.startswith("cash/") or field in {"starts_on", "opening_cash", "coverage_through"}:
        return RecordCategory.CASH_FLOW
    if field.startswith("sale."):
        return RecordCategory.HARVEST
    if field.startswith("repayment/") or field == "financing.repayment_on":
        return RecordCategory.REPAYMENT_SCHEDULE
    if field.startswith("financing."):
        return RecordCategory.CREDIT_TERMS
    return None


def get_records(brief: CaseBrief, categories: tuple[str, ...]) -> CaseRecords:
    """Availability means recorded evidence exists, not that it has been verified.

    Unknown categories are caller errors. Known categories with no captured
    evidence are explicitly unavailable; no external retrieval is implied.
    """
    if not isinstance(categories, (tuple, list)) or not categories:
        raise ValueError("Request at least one supported evidence category.")
    requested = tuple(RecordCategory(category) for category in categories)
    if len(set(requested)) != len(requested):
        raise ValueError("Request each evidence category only once.")
    groups = []
    for category in requested:
        records = tuple(r for r in brief.sources if _category(r.input.field) == category)
        gaps = tuple(g for g in brief.gaps if _category(g.field) == category)
        if not records:
            status = RecordStatus.UNAVAILABLE
            explanation = "No source records for this category are captured in this saved version."
        elif any(g.reason == "conflicting sources" for g in gaps):
            status = RecordStatus.CONFLICTING
            explanation = "Sources disagree; officer clarification is required."
        elif gaps:
            status = RecordStatus.INCOMPLETE
            explanation = "Records exist but have unresolved evidence gaps."
        else:
            status = RecordStatus.AVAILABLE
            explanation = "Recorded sources are available; this does not establish their accuracy or freshness."
        groups.append(RecordGroup(category, status, records, gaps, explanation))
    return CaseRecords(
        brief.assessment_id,
        brief.case_id,
        brief.version,
        tuple(groups),
        brief.limitations,
    )
