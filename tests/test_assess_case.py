# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2026 MathaiMarvin

"""Case conversion tests; fixtures are synthetic and carry no policy verdict."""

import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal

from farmcredit.application.assess_case import assess_case
from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.seasonal_case import HarvestSale, SeasonalCase, SupplierFinancing

D = Decimal


def fixture(received_on=date(2027, 9, 10)):
    return SeasonalCase(
        starts_on=date(2027, 4, 1),
        opening_cash=D("40000"),
        sale=HarvestSale(
            "sale", date(2027, 9, 1), received_on, D("2000"), D("400"), D("100"), D("40")
        ),
        financing=SupplierFinancing(
            "package", date(2027, 4, 2), D("20000"), D("2000"), date(2027, 9, 30)
        ),
        other_movements=(
            CashMovement("april-cost", date(2027, 4, 10), D("-6000")),
            CashMovement("june-cost", date(2027, 6, 10), D("-6000")),
            CashMovement("harvest-cost", date(2027, 9, 1), D("-3000")),
            CashMovement("selling-cost", date(2027, 9, 2), D("-3000")),
            CashMovement("existing-debt", date(2027, 8, 15), D("-5000")),
            *(CashMovement(f"household-{m}", date(2027, m, 25), D("-2500")) for m in range(4, 10)),
        ),
    )


class AssessCaseTests(unittest.TestCase):
    def test_case_conversion_preserves_both_expected_outcomes(self):
        for receipt, before, after in (
            (date(2027, 9, 10), "62000", "40000"),
            (date(2027, 10, 15), "2000", "-20000"),
        ):
            with self.subTest(receipt=receipt):
                result = assess_case(fixture(receipt))
                self.assertEqual(result.cash_before_repayment, D(before))
                self.assertEqual(result.cash_after_repayment, D(after))

    def test_retained_harvest_is_not_sold(self):
        case = fixture()
        result = assess_case(replace(case, sale=replace(case.sale, retained_kg=D("500"))))
        self.assertEqual(result.cash_after_repayment, D("36000"))

    def test_impossible_or_unknown_harvest_is_rejected(self):
        case = fixture()
        for change in (
            {"lost_kg": D("1700")},
            {"gross_kg": None},
            {"retained_kg": D("-1")},
            {"price_per_kg": D("NaN")},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess_case(replace(case, sale=replace(case.sale, **change)))

    def test_duplicate_financed_package_cannot_be_charged_as_cash(self):
        case = fixture()
        duplicate = CashMovement("package", date(2027, 4, 2), D("-20000"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_case(replace(case, other_movements=(*case.other_movements, duplicate)))

    def test_invalid_financing_is_rejected(self):
        case = fixture()
        for change in (
            {"principal": D("0")},
            {"charges": D("-1")},
            {"repayment_on": date(2027, 8, 1)},
            {"supplied_on": date(2027, 3, 1)},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                assess_case(replace(case, financing=replace(case.financing, **change)))

    def test_preharvest_receipt_is_not_treated_as_sale(self):
        with self.assertRaisesRegex(ValueError, "Pre-harvest"):
            assess_case(fixture(date(2027, 8, 1)))

    def test_case_snapshots_cash_movement_collection(self):
        case = fixture()
        source = list(case.other_movements)
        snapshot = replace(case, other_movements=source)
        source.clear()
        self.assertEqual(len(snapshot.other_movements), 11)
