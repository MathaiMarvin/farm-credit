# SPDX-License-Identifier: AGPL-3.0-only
"""Human advisory review rules, independent of authentication and storage."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Officer:
    user_id: str
    name: str
    may_review: bool


@dataclass(frozen=True)
class ReviewRequest:
    assessment_id: str
    operation_id: str
    expected_revision: int
    decision: str
    note: str
    officer: Officer


@dataclass(frozen=True)
class AdvisoryReview:
    operation_id: str
    assessment_id: str
    case_revision: int
    decision: str
    note: str
    officer_id: str
    officer_name: str
    reviewed_at: str

    @property
    def reviewed_on(self) -> datetime:
        return datetime.fromisoformat(self.reviewed_at)


def validate_review(
    request: ReviewRequest,
    *,
    latest: bool,
    saved_fingerprint: str,
    current_fingerprint: str | None,
    current_revision: int,
    already_reviewed: bool,
) -> None:
    if (
        not request.officer.may_review
        or not request.officer.user_id
        or not request.officer.name.strip()
    ):
        raise ValueError("A named, authorised officer must review the advisory.")
    if request.decision not in ("approved", "changes_requested"):
        raise ValueError("Choose approve advisory or request changes.")
    if len(request.note) > 2000 or (
        request.decision == "changes_requested" and not request.note.strip()
    ):
        raise ValueError("Requests for changes need a reason of at most 2000 characters.")
    if already_reviewed:
        raise ValueError("This version has already been reviewed. Save a new assessment version.")
    if not latest or current_fingerprint != saved_fingerprint:
        raise ValueError("This assessment is stale. Recalculate and save the current case.")
    if request.expected_revision != current_revision:
        raise ValueError("The case changed while this review was open. Reopen the assessment.")
