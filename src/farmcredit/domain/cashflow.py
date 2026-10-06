# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Project available KES cash against a supplied repayment schedule.

Inputs are dated household cash movements, not accounting revenue or expense.
Supplier-financed inputs therefore do not enter this cash ledger. Their eventual
repayment does. Evidence validation and financing normalisation belong upstream.
"""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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
class RepaymentPosition:
    on: date
    due: Decimal
    cash_before: Decimal
    cash_after: Decimal


@dataclass(frozen=True)
class CashflowResult:
    cash_before_repayment: Decimal
    cash_after_repayment: Decimal
    coverage: Decimal
    balances: tuple[CashBalance, ...]
    future_movements: tuple[CashMovement, ...]
    repayments: tuple[RepaymentPosition, ...] = ()

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
    """Compatibility entry point for a single supplied repayment."""
    return assess_schedule(
        starts_on=starts_on,
        opening_cash=opening_cash,
        movements=movements,
        repayments=(repayment,),
    )


def assess_schedule(
    *,
    starts_on: date,
    opening_cash: Decimal,
    movements: Iterable[CashMovement],
    repayments: Iterable[CashMovement],
) -> CashflowResult:
    """Assess dated obligations, reserving other same-day outflows first.

    Negative balances carry forward as unmet obligations, never as borrowing.
    Same-day proposed instalments are grouped; no intraday ordering is inferred.
    The summary fields describe the final repayment date, not schedule-wide coverage.
    """
    if type(starts_on) is not date:
        raise ValueError("Assessment needs a calendar start date.")
    validate_money(opening_cash)
    if opening_cash < ZERO:
        raise ValueError("Opening available cash cannot be negative.")
    repayments = tuple(repayments)
    if not repayments:
        raise ValueError("A repayment schedule cannot be empty.")
    if any(item.amount >= ZERO or item.on < starts_on for item in repayments):
        raise ValueError("Repayment must be an outflow on or after the start date.")
    entries = tuple(movements)
    ids = [entry.record_id for entry in (*entries, *repayments)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate source record; a movement may only be counted once.")
    if any(entry.on < starts_on for entry in entries):
        raise ValueError("Exclude payments already reflected in opening cash.")
    final_date = max(item.on for item in repayments)
    due_by_date = {}
    for item in repayments:
        due_by_date[item.on] = due_by_date.get(item.on, ZERO) - item.amount
    ordered = sorted((*entries, *repayments), key=lambda entry: entry.on)
    balance = opening_cash
    balances = [CashBalance(starts_on, opening_cash)]
    positions = []
    for on, group in groupby(ordered, key=lambda entry: entry.on):
        if on > final_date:
            break
        amounts = [entry.amount for entry in group]
        if any(amount > ZERO for amount in amounts) and any(amount < ZERO for amount in amounts):
            raise ValueError(f"Receipt/payment ordering on {on} requires clarification.")
        balance += sum(amounts, ZERO)
        balances.append(CashBalance(on, balance))
        if on in due_by_date:
            due = due_by_date[on]
            positions.append(RepaymentPosition(on, due, balance + due, balance))
    last = positions[-1]
    return CashflowResult(
        cash_before_repayment=last.cash_before,
        cash_after_repayment=last.cash_after,
        coverage=(last.cash_before / last.due).quantize(CENT, rounding=ROUND_HALF_UP),
        balances=tuple(balances),
        future_movements=tuple(entry for entry in ordered if entry.on > final_date),
        repayments=tuple(positions),
    )
