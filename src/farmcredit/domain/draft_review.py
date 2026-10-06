# SPDX-License-Identifier: AGPL-3.0-only
"""Named human decisions on exact advisory draft versions."""

from dataclasses import dataclass

from farmcredit.domain.review import Officer


@dataclass(frozen=True)
class DraftReviewRequest:
    draft_id: str
    operation_id: str
    expected_revision: int
    decision: str
    note: str
    officer: Officer


def validate_draft_review(
    request: DraftReviewRequest, *, current: bool, revision: int, already_reviewed: bool
) -> None:
    if (
        not request.officer.may_review
        or not request.officer.user_id
        or not request.officer.name.strip()
    ):
        raise ValueError("A named, authorised officer must review the draft.")
    if not request.operation_id or len(request.operation_id) > 64:
        raise ValueError("A valid review identifier is required.")
    if request.decision not in {"approved", "changes_requested"}:
        raise ValueError("Choose approve draft or request changes.")
    if len(request.note) > 2000 or (
        request.decision == "changes_requested" and not request.note.strip()
    ):
        raise ValueError("Requests for changes need a reason of at most 2000 characters.")
    if already_reviewed:
        raise ValueError("This draft has already been reviewed. Open the saved decision.")
    if not current:
        raise ValueError(
            "This draft is historical. Review a new draft based on the current saved assessment."
        )
    if request.expected_revision != revision:
        raise ValueError("The case changed while this review was open. Reopen the draft.")
