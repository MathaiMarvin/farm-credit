# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit sensitivity tests, derived from an evidence-checked baseline."""

from dataclasses import dataclass, replace
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

from farmcredit.application.assess_case import assess_case
from farmcredit.application.assess_evidence import SourcedAssessment, assess_sourced_case
from farmcredit.domain.cashflow import CENT, CashflowResult
from farmcredit.domain.evidence import EvidenceRecord
from farmcredit.domain.seasonal_case import SeasonalCase


@dataclass(frozen=True)
class StressAssumptions:
    price_reduction: Decimal
    harvest_reduction: Decimal

    def __post_init__(self):
        for value in (self.price_reduction, self.harvest_reduction):
            if not isinstance(value, Decimal) or not value.is_finite() or not 0 <= value <= 100:
                raise ValueError("Stress reductions must be finite percentages from 0 to 100.")


@dataclass(frozen=True)
class StressScenario:
    label: str
    assumptions: StressAssumptions
    case: SeasonalCase
    cashflow: CashflowResult | None
    error: str | None


@dataclass(frozen=True)
class StressComparison:
    baseline: SourcedAssessment
    scenarios: tuple[StressScenario, ...]


def compare_stress(
    case: SeasonalCase,
    records: Iterable[EvidenceRecord],
    assumptions: StressAssumptions,
    *,
    as_of: date,
) -> StressComparison:
    baseline = assess_sourced_case(case, records, as_of=as_of)
    if baseline.issues:
        return StressComparison(baseline, ())
    scenarios = []
    for label, reductions in (
        ("Lower price", StressAssumptions(assumptions.price_reduction, Decimal(0))),
        ("Lower harvest", StressAssumptions(Decimal(0), assumptions.harvest_reduction)),
        ("Combined stress", assumptions),
    ):
        # Retained food, losses, dates, costs and obligations remain unchanged.
        sale = replace(
            case.sale,
            price_per_kg=(case.sale.price_per_kg * (1 - reductions.price_reduction / 100)).quantize(
                CENT, rounding=ROUND_HALF_UP
            ),
            gross_kg=case.sale.gross_kg * (1 - reductions.harvest_reduction / 100),
        )
        stressed = replace(case, sale=sale)
        try:
            result = assess_case(stressed)
            error = None
        except ValueError as exception:
            result, error = None, str(exception)
        scenarios.append(StressScenario(label, reductions, stressed, result, error))
    return StressComparison(baseline, tuple(scenarios))
