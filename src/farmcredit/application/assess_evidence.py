# SPDX-License-Identifier: AGPL-3.0-only
"""Gate the case calculation on traceable input snapshots."""

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from farmcredit.application.assess_case import assess_case
from farmcredit.domain.cashflow import CashflowResult
from farmcredit.domain.evidence import EvidenceIssue, EvidenceRecord, InputValue, review_evidence
from farmcredit.domain.seasonal_case import SeasonalCase


def case_inputs(case: SeasonalCase) -> tuple[InputValue, ...]:
    """Enumerate the dates and amounts consumed by the seasonal calculator."""
    values = [
        InputValue("starts_on", case.starts_on, "date"),
        InputValue("opening_cash", case.opening_cash, "KES"),
        InputValue("sale.harvest_on", case.sale.harvest_on, "date"),
        InputValue("sale.received_on", case.sale.received_on, "date"),
        InputValue("sale.gross_kg", case.sale.gross_kg, "kg"),
        InputValue("sale.retained_kg", case.sale.retained_kg, "kg"),
        InputValue("sale.lost_kg", case.sale.lost_kg, "kg"),
        InputValue("sale.price_per_kg", case.sale.price_per_kg, "KES/kg"),
        InputValue("financing.supplied_on", case.financing.supplied_on, "date"),
        InputValue("financing.principal", case.financing.principal, "KES"),
        InputValue("financing.charges", case.financing.charges, "KES"),
        InputValue("financing.repayment_on", case.financing.repayment_on, "date"),
    ]
    if case.coverage_through is not None:
        values.append(InputValue("coverage_through", case.coverage_through, "date"))
    for instalment in case.financing.schedule:
        values.extend(
            (
                InputValue(f"repayment/{instalment.record_id}/on", instalment.on, "date"),
                InputValue(f"repayment/{instalment.record_id}/amount", instalment.amount, "KES"),
            )
        )
    for movement in case.other_movements:
        values.extend(
            (
                InputValue(f"cash/{movement.record_id}/on", movement.on, "date"),
                InputValue(f"cash/{movement.record_id}/amount", movement.amount, "KES"),
            )
        )
    return tuple(values)


@dataclass(frozen=True)
class SourcedAssessment:
    records: tuple[EvidenceRecord, ...]
    issues: tuple[EvidenceIssue, ...]
    cashflow: CashflowResult | None


def assess_sourced_case(
    case: SeasonalCase, records: Iterable[EvidenceRecord], *, as_of: date
) -> SourcedAssessment:
    snapshot = tuple(records)
    issues = review_evidence(case_inputs(case), snapshot, as_of=as_of)
    return SourcedAssessment(snapshot, issues, None if issues else assess_case(case))
