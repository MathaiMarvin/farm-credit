# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic records only; no customer records or external observations."""

from datetime import date
from decimal import Decimal

from farmcredit.application.assess_evidence import case_inputs
from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.evidence import EvidenceBasis, EvidenceRecord
from farmcredit.domain.seasonal_case import HarvestSale, SeasonalCase, SupplierFinancing

DEMO_RECORDED_ON = date(2026, 10, 5)


def load_demo_evidence() -> tuple[EvidenceRecord, ...]:
    """Synthetic source snapshots, always generated from the original fixture.

    Never pass a changed case here to manufacture support for edited values.
    Every value is an assumption, including the simulated opening balance.
    """
    return tuple(
        EvidenceRecord(
            record_id=f"demo:{item.field}",
            input=item,
            source="Synthetic cooperative planning worksheet",
            recorded_on=DEMO_RECORDED_ON,
            basis=EvidenceBasis.ASSUMED,
            synthetic=True,
        )
        for item in case_inputs(load_demo_case())
    )


def load_demo_case() -> SeasonalCase:
    return SeasonalCase(
        starts_on=date(2027, 4, 1),
        opening_cash=Decimal("40000"),
        sale=HarvestSale(
            "sale",
            date(2027, 9, 1),
            date(2027, 9, 10),
            Decimal("2000"),
            Decimal("400"),
            Decimal("100"),
            Decimal("40"),
        ),
        financing=SupplierFinancing(
            "package", date(2027, 4, 2), Decimal("20000"), Decimal("2000"), date(2027, 9, 30)
        ),
        other_movements=(
            CashMovement("production-april", date(2027, 4, 10), Decimal("-6000")),
            CashMovement("production-june", date(2027, 6, 10), Decimal("-6000")),
            CashMovement("production-september", date(2027, 9, 1), Decimal("-3000")),
            CashMovement("selling-costs", date(2027, 9, 2), Decimal("-3000")),
            CashMovement("existing-debt", date(2027, 8, 15), Decimal("-5000")),
            *(
                CashMovement(f"household-{month}", date(2027, month, 25), Decimal("-2500"))
                for month in range(4, 10)
            ),
        ),
    )
