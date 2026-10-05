# SPDX-License-Identifier: AGPL-3.0-only
"""Trace input values to records without treating provenance as verification."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Iterable


class EvidenceBasis(str, Enum):
    OBSERVED = "observed"
    DECLARED = "declared"
    ASSUMED = "assumed"


@dataclass(frozen=True)
class InputValue:
    field: str
    value: Decimal | date
    unit: str

    def __post_init__(self):
        if not isinstance(self.field, str) or not self.field.strip():
            raise ValueError("An input needs a field name.")
        if isinstance(self.value, Decimal):
            if (
                not self.value.is_finite()
                or not isinstance(self.unit, str)
                or not self.unit.strip()
            ):
                raise ValueError("Numeric inputs need a finite Decimal and an explicit unit.")
        elif type(self.value) is not date or self.unit != "date":
            raise ValueError("An input must be a Decimal with units or a calendar date.")


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    input: InputValue
    source: str
    recorded_on: date
    basis: EvidenceBasis
    synthetic: bool

    def __post_init__(self):
        for text in (self.record_id, self.source):
            if not isinstance(text, str) or not text.strip() or text != text.strip():
                raise ValueError("Evidence needs a nonblank source and record ID without padding.")
        if not isinstance(self.input, InputValue):
            raise ValueError("Evidence must snapshot a typed input value.")
        if type(self.recorded_on) is not date:
            raise ValueError("Evidence needs a calendar recording date.")
        if not isinstance(self.basis, EvidenceBasis) or type(self.synthetic) is not bool:
            raise ValueError("Evidence basis and synthetic status must be explicit.")


@dataclass(frozen=True)
class EvidenceIssue:
    field: str
    reason: str
    record_ids: tuple[str, ...]


def review_evidence(
    inputs: Iterable[InputValue], records: Iterable[EvidenceRecord], *, as_of: date
) -> tuple[EvidenceIssue, ...]:
    """Require matching, nonconflicting records for each supplied input.

    A matching record is not proof of truth or freshness. as_of is provided by
    the caller so replay does not depend on today's date. Planned event dates
    may be future; source recording dates must not be future at review time.
    """
    if type(as_of) is not date:
        raise ValueError("Evidence review needs a calendar date.")
    expected = tuple(inputs)
    records = tuple(records)
    if len({item.field for item in expected}) != len(expected):
        raise ValueError("Duplicate input fields would hide evidence requirements.")
    if len({record.record_id for record in records}) != len(records):
        raise ValueError("Duplicate evidence record IDs are not allowed.")
    fields = {item.field for item in expected}
    issues = []
    for record in records:
        if record.input.field not in fields:
            issues.append(EvidenceIssue(record.input.field, "unknown input", (record.record_id,)))
        if record.recorded_on > as_of:
            issues.append(
                EvidenceIssue(record.input.field, "recorded after review date", (record.record_id,))
            )
    for item in expected:
        matching = tuple(record for record in records if record.input.field == item.field)
        ids = tuple(record.record_id for record in matching)
        if not matching:
            issues.append(EvidenceIssue(item.field, "missing source", ()))
        elif len({(record.input.value, record.input.unit) for record in matching}) > 1:
            issues.append(EvidenceIssue(item.field, "conflicting sources", ids))
        elif any(record.input != item for record in matching):
            issues.append(EvidenceIssue(item.field, "source does not match current input", ids))
    return tuple(issues)
