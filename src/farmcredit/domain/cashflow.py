# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Project available KES cash against one proposed seasonal repayment.

Inputs are dated household cash movements, not accounting revenue or expense.
Supplier-financed inputs therefore do not enter this cash ledger. Their eventual
repayment does. Evidence validation and financing normalisation belong upstream.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from itertools import groupby
from typing import Iterable


ZERO = Decimal("0.00")
CENT = Decimal("0.01")


def validate_money(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError("Money must be a finite Decimal.")
    try:
        rounded = value.quantize(CENT)
    except InvalidOperation as error:
        raise ValueError("Money exceeds supported decimal precision.") from error
    if value != rounded:
        raise ValueError("KES amounts must have at most two decimal places.")


@dataclass(frozen=True)
class CashMovement:
    """A sourced cash receipt (positive) or payment (negative)."""

    record_id: str
    on: date
    amount: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.record_id, str) or not self.record_id.strip():
            raise ValueError("A cash movement needs a source record ID.")
        if self.record_id != self.record_id.strip():
            raise ValueError("Source record IDs cannot contain surrounding whitespace.")
        if type(self.on) is not date:
            raise ValueError("Cash movements need a calendar date.")
        validate_money(self.amount)


@dataclass(frozen=True)
class CashBalance:
    on: date
    amount: Decimal


@dataclass(frozen=True)
class CashflowResult:
    cash_before_repayment: Decimal
    cash_after_repayment: Decimal
    coverage: Decimal
    balances: tuple[CashBalance, ...]
    future_movements: tuple[CashMovement, ...]

    @property
    def shortfalls(self) -> tuple[CashBalance, ...]:
        """Negative balances represent unmet obligations, never an overdraft."""
        return tuple(balance for balance in self.balances if balance.amount < ZERO)


def assess_cashflow(
    *,
    starts_on: date,
    opening_cash: Decimal,
    movements: Iterable[CashMovement],
    repayment: CashMovement,
) -> CashflowResult:
    """Assess known cash flows through repayment, retaining later evidence.

    Opening cash is available at the start of starts_on. The proposed repayment
    is supplied separately and must not also appear in movements. Mixed receipts
    and payments on one date require clarification in this first version: date
    alone cannot establish that a receipt is available before a payment.
    """
    if type(starts_on) is not date:
        raise ValueError("Assessment needs a calendar start date.")
    validate_money(opening_cash)
    if opening_cash < ZERO:
        raise ValueError("Opening available cash cannot be negative.")
    if repayment.amount >= ZERO or repayment.on < starts_on:
        raise ValueError("Repayment must be an outflow on or after the start date.")

    entries = tuple(movements)
    ids = [entry.record_id for entry in (*entries, repayment)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source record; a movement may only be counted once.")
    if any(entry.on < starts_on for entry in entries):
        raise ValueError("Exclude payments already reflected in opening cash.")

    ordered = sorted((*entries, repayment), key=lambda entry: entry.on)
    balance = opening_cash
    balances = [CashBalance(starts_on, opening_cash)]
    for on, group in groupby(ordered, key=lambda entry: entry.on):
        if on > repayment.on:
            break
        amounts = [entry.amount for entry in group]
        if any(amount > ZERO for amount in amounts) and any(amount < ZERO for amount in amounts):
            raise ValueError(f"Receipt/payment ordering on {on} requires clarification.")
        balance += sum(amounts, ZERO)
        balances.append(CashBalance(on, balance))

    # Other payments on the due date are reserved before proposed repayment.
    before = balance - repayment.amount
    coverage = (before / -repayment.amount).quantize(CENT, rounding=ROUND_HALF_UP)
    return CashflowResult(
        cash_before_repayment=before,
        cash_after_repayment=balance,
        coverage=coverage,
        balances=tuple(balances),
        future_movements=tuple(entry for entry in ordered if entry.on > repayment.on),
    )
