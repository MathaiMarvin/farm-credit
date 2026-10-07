# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Convert a supplied seasonal case into a deterministic cash-flow assessment."""

from datetime import date

from farmcredit.domain.cashflow import CashflowResult, assess_schedule
from farmcredit.domain.seasonal_case import SeasonalCase


def assess_case(case: SeasonalCase) -> CashflowResult:
    """Calculate supplied facts; this does not verify evidence or approve credit.

    other_movements contains only actual household cash movements. The supplier
    package is represented by financing and must not also appear as a cost.
    This first case model excludes cash disbursements and separately timed fees.
    """
    sale = case.sale.as_receipt()
    repayments = case.financing.as_repayments()
    if any(item.record_id == case.financing.record_id for item in case.other_movements):
        raise ValueError("Duplicate financed package cannot be charged as a cash movement.")
    if type(case.starts_on) is not date:
        raise ValueError("Case start needs a calendar date.")
    if case.financing.supplied_on < case.starts_on:
        raise ValueError("Financing already in progress is outside this case model.")
    if case.sale.harvest_on < case.financing.supplied_on:
        raise ValueError("The financed package must precede or coincide with harvest.")
    if not case.financing.schedule and repayments[0].on < case.sale.harvest_on:
        raise ValueError("Only repayment on or after harvest is supported.")
    if case.financing.schedule and (
        type(case.coverage_through) is not date
        or case.coverage_through < case.financing.repayment_on
    ):
        raise ValueError("Confirm household cash-flow coverage through the final instalment.")
    return assess_schedule(
        starts_on=case.starts_on,
        opening_cash=case.opening_cash,
        movements=(*case.other_movements, sale),
        repayments=repayments,
    )
