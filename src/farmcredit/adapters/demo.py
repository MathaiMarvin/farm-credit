# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic records only; no customer records or external observations."""

from datetime import date
from decimal import Decimal

from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.seasonal_case import HarvestSale, SeasonalCase, SupplierFinancing


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
