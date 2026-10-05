# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Convert a supplied seasonal case into a deterministic cash-flow assessment."""

from datetime import date

from farmcredit.domain.cashflow import CashflowResult, assess_cashflow
from farmcredit.domain.seasonal_case import SeasonalCase


def assess_case(case: SeasonalCase) -> CashflowResult:
    """Calculate supplied facts; this does not verify evidence or approve credit.

    other_movements contains only actual household cash movements. The supplier
    package is represented by financing and must not also appear as a cost.
    This first case model excludes cash disbursements and separately timed fees.
    """
    sale = case.sale.as_receipt()
    repayment = case.financing.as_repayment()
    if type(case.starts_on) is not date:
        raise ValueError("Case start needs a calendar date.")
    if case.financing.supplied_on < case.starts_on:
        raise ValueError("Financing already in progress is outside this case model.")
    if case.sale.harvest_on < case.financing.supplied_on:
        raise ValueError("The financed package must precede or coincide with harvest.")
    if repayment.on < case.sale.harvest_on:
        raise ValueError("Only repayment on or after harvest is supported.")
    return assess_cashflow(
        starts_on=case.starts_on,
        opening_cash=case.opening_cash,
        movements=(*case.other_movements, sale),
        repayment=repayment,
    )
