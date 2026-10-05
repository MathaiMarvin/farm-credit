# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Typed inputs for one seasonal maize case with direct supplier financing."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from farmcredit.domain.cashflow import CENT, CashMovement, validate_money


@dataclass(frozen=True)
class HarvestSale:
    record_id: str
    harvest_on: date
    received_on: date
    gross_kg: Decimal
    retained_kg: Decimal
    lost_kg: Decimal
    price_per_kg: Decimal

    def as_receipt(self) -> CashMovement:
        for quantity in (self.gross_kg, self.retained_kg, self.lost_kg):
            if not isinstance(quantity, Decimal) or not quantity.is_finite() or quantity < 0:
                raise ValueError("Harvest quantities must be finite nonnegative Decimals.")
        saleable = self.gross_kg - self.retained_kg - self.lost_kg
        if saleable < 0:
            raise ValueError("Retained harvest and losses exceed gross harvest.")
        validate_money(self.price_per_kg)
        if self.price_per_kg < 0:
            raise ValueError("Sale price cannot be negative.")
        if type(self.harvest_on) is not date or type(self.received_on) is not date:
            raise ValueError("Harvest and receipt need calendar dates.")
        if self.received_on < self.harvest_on:
            raise ValueError("Pre-harvest sales financing is outside this case model.")
        amount = (saleable * self.price_per_kg).quantize(CENT, rounding=ROUND_HALF_UP)
        return CashMovement(self.record_id, self.received_on, amount)


@dataclass(frozen=True)
class SupplierFinancing:
    """One supplier-paid package; charges are all payable at final repayment."""

    record_id: str
    supplied_on: date
    principal: Decimal
    charges: Decimal
    repayment_on: date

    def as_repayment(self) -> CashMovement:
        validate_money(self.principal)
        validate_money(self.charges)
        if self.principal <= 0 or self.charges < 0:
            raise ValueError("Principal must be positive and charges nonnegative.")
        if type(self.supplied_on) is not date or type(self.repayment_on) is not date:
            raise ValueError("Financing needs calendar dates.")
        if self.repayment_on < self.supplied_on:
            raise ValueError("Repayment cannot precede input supply.")
        return CashMovement(self.record_id, self.repayment_on, -(self.principal + self.charges))


@dataclass(frozen=True)
class SeasonalCase:
    starts_on: date
    opening_cash: Decimal
    sale: HarvestSale
    financing: SupplierFinancing
    other_movements: tuple[CashMovement, ...]

    def __post_init__(self) -> None:
        # Snapshot the caller's collection, including when supplied as a list.
        object.__setattr__(self, "other_movements", tuple(self.other_movements))
