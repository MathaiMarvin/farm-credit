# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic calculations over server-resolved immutable inputs."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Callable

from farmcredit.application.get_case import CaseScope, InvalidCaseSnapshot, get_case
from farmcredit.application.saved_assessments import (
    POLICY_VERSION,
    SavedAssessment,
    input_fingerprint,
)
from farmcredit.application.stress_scenarios import (
    StressAssumptions,
    StressComparison,
    compare_stress,
)
from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.evidence import EvidenceIssue
from farmcredit.domain.seasonal_case import HarvestSale, SeasonalCase, SupplierFinancing


@dataclass(frozen=True)
class Calculation:
    calculation_id: str
    assessment_id: str
    case_id: str
    version: int
    policy_version: str
    evidence_as_of: date
    assumptions: StressAssumptions
    comparison: StressComparison | None
    issues: tuple[EvidenceIssue, ...]
    error: str | None
    limitations: tuple[str, ...]


def _movement(row: dict) -> CashMovement:
    return CashMovement(row["record_id"], date.fromisoformat(row["on"]), Decimal(row["amount"]))


def _restore_case(row: dict) -> SeasonalCase:
    sale, financing = row["sale"], row["financing"]
    return SeasonalCase(
        starts_on=date.fromisoformat(row["starts_on"]),
        opening_cash=Decimal(row["opening_cash"]),
        coverage_through=date.fromisoformat(row["coverage_through"])
        if row["coverage_through"]
        else None,
        sale=HarvestSale(
            sale["record_id"],
            date.fromisoformat(sale["harvest_on"]),
            date.fromisoformat(sale["received_on"]),
            Decimal(sale["gross_kg"]),
            Decimal(sale["retained_kg"]),
            Decimal(sale["lost_kg"]),
            Decimal(sale["price_per_kg"]),
        ),
        financing=SupplierFinancing(
            financing["record_id"],
            date.fromisoformat(financing["supplied_on"]),
            Decimal(financing["principal"]),
            Decimal(financing["charges"]),
            date.fromisoformat(financing["repayment_on"]),
            tuple(_movement(item) for item in financing["schedule"]),
            financing["schedule_source"],
            financing["schedule_version"],
        ),
        other_movements=tuple(_movement(item) for item in row["other_movements"]),
    )


def assess_cashflow(
    scope: CaseScope,
    read_saved: Callable[[str], SavedAssessment | None],
    assumptions: StressAssumptions,
) -> Calculation:
    """Recompute from saved inputs, never trust saved totals or caller loan terms.

    The content-derived ID identifies this calculation, not a persisted run or
    approval. Draft persistence must resolve and verify these inputs again.
    """
    if not isinstance(assumptions, StressAssumptions):
        raise ValueError("Explicit validated stress assumptions are required.")
    saved = read_saved(scope.assessment_id)
    brief = get_case(scope, lambda key: saved)
    if brief.policy_version != POLICY_VERSION:
        raise InvalidCaseSnapshot("Saved policy is not supported by the current calculator.")
    identity = {
        "assessment_id": brief.assessment_id,
        "case_id": brief.case_id,
        "version": brief.version,
        "input_fingerprint": brief.input_fingerprint,
        "policy_version": POLICY_VERSION,
        "evidence_as_of": scope.evidence_as_of,
        "assumptions": assumptions,
    }
    comparison, error = None, None
    if not brief.gaps:
        try:
            case = _restore_case(saved.snapshot["inputs"]["case"])
        except (KeyError, TypeError, ValueError) as exception:
            raise InvalidCaseSnapshot("Saved case inputs cannot be restored.") from exception
        try:
            comparison = compare_stress(
                case, brief.sources, assumptions, as_of=scope.evidence_as_of
            )
        except ValueError as exception:
            error = str(exception)
    return Calculation(
        input_fingerprint(identity),
        brief.assessment_id,
        brief.case_id,
        brief.version,
        POLICY_VERSION,
        scope.evidence_as_of,
        assumptions,
        comparison,
        brief.gaps,
        error,
        (*brief.limitations, "Calculation findings are not credit eligibility or loan approval."),
    )
