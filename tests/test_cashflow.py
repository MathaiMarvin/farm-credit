"""Synthetic calculation fixtures from docs/workflow.md; no agent results."""

import unittest
from datetime import date
from decimal import Decimal

from farmcredit.domain.cashflow import CashMovement, assess_cashflow


D = Decimal
START = date(2027, 4, 1)
REPAYMENT = CashMovement("proposed-repayment", date(2027, 9, 30), D("-22000"))


def seasonal_movements(received_on: date) -> list[CashMovement]:
    saleable_kg = D("2000") - D("400") - D("100")
    return [
        CashMovement("production-april", date(2027, 4, 10), D("-6000")),
        CashMovement("production-june", date(2027, 6, 10), D("-6000")),
        CashMovement("production-september", date(2027, 9, 1), D("-3000")),
        CashMovement("existing-debt", date(2027, 8, 15), D("-5000")),
        CashMovement("selling-costs", date(2027, 9, 2), D("-3000")),
        CashMovement("sale", received_on, saleable_kg * D("40")),
        *[
            CashMovement(f"household-{month}", date(2027, month, 25), D("-2500"))
            for month in range(4, 10)
        ],
    ]


def assess(movements, opening_cash=D("40000")):
    return assess_cashflow(
        starts_on=START, opening_cash=opening_cash,
        movements=movements, repayment=REPAYMENT,
    )


class CashflowTests(unittest.TestCase):
    def test_receipt_before_deadline_leaves_cash(self):
        result = assess(seasonal_movements(date(2027, 9, 10)))
        self.assertEqual(result.cash_before_repayment, D("62000"))
        self.assertEqual(result.cash_after_repayment, D("40000"))
        self.assertEqual(result.coverage, D("2.82"))
        self.assertEqual(result.shortfalls, ())
        self.assertEqual(result.future_movements, ())

    def test_late_receipt_is_visible_but_cannot_fund_repayment(self):
        result = assess(seasonal_movements(date(2027, 10, 15)))
        self.assertEqual(result.cash_before_repayment, D("2000"))
        self.assertEqual(result.cash_after_repayment, D("-20000"))
        self.assertEqual(result.coverage, D("0.09"))
        self.assertEqual([(b.on, b.amount) for b in result.shortfalls],
                         [(REPAYMENT.on, D("-20000"))])
        self.assertEqual([m.record_id for m in result.future_movements], ["sale"])

    def test_later_surplus_does_not_hide_earlier_shortfall(self):
        result = assess([
            CashMovement("cost", date(2027, 4, 2), D("-50000")),
            CashMovement("receipt", date(2027, 9, 10), D("60000")),
        ])
        self.assertEqual(result.cash_after_repayment, D("28000"))
        self.assertEqual(result.shortfalls[0].amount, D("-10000"))

    def test_duplicate_repayment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess([REPAYMENT])

    def test_paid_cost_before_opening_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "opening cash"):
            assess([CashMovement("old-cost", date(2027, 3, 31), D("-100"))])

    def test_same_day_receipt_requires_ordering(self):
        with self.assertRaisesRegex(ValueError, "ordering"):
            assess(seasonal_movements(REPAYMENT.on))

    def test_invalid_money_is_rejected(self):
        for amount in (0.1, D("NaN"), D("Infinity"), D("1.001"), D("1e100")):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                CashMovement("invalid", START, amount)

    def test_invalid_record_ids_are_rejected(self):
        for record_id in (None, "", " ", " sale"):
            with self.subTest(record_id=record_id), self.assertRaises(ValueError):
                CashMovement(record_id, START, D("10"))

    def test_other_due_date_obligations_are_reserved_before_repayment(self):
        result = assess([CashMovement("other-debt", REPAYMENT.on, D("-25000"))])
        self.assertEqual(result.cash_before_repayment, D("15000"))
        self.assertEqual(result.cash_after_repayment, D("-7000"))

    def test_exact_repayment_leaves_zero_without_shortfall(self):
        result = assess([], opening_cash=D("22000"))
        self.assertEqual(result.cash_after_repayment, D("0"))
        self.assertEqual(result.shortfalls, ())
        self.assertEqual(result.coverage, D("1.00"))

    def test_ratio_uses_half_up_rounding(self):
        self.assertEqual(assess([], opening_cash=D("22110")).coverage, D("1.01"))

    def test_repayment_must_be_positive_obligation(self):
        for amount in (D("0"), D("22000")):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                assess_cashflow(starts_on=START, opening_cash=D("40000"),
                                movements=[], repayment=CashMovement("repay", REPAYMENT.on, amount))

    def test_cash_financing_and_supplier_financing_have_equal_result(self):
        # Cash arrives before purchase; direct supplier funding has no cash entries.
        cash_funded = assess([
            CashMovement("loan-cash", date(2027, 4, 2), D("20000")),
            CashMovement("input-purchase", date(2027, 4, 3), D("-20000")),
        ])
        supplier_funded = assess([])
        self.assertEqual(cash_funded.cash_after_repayment, supplier_funded.cash_after_repayment)

    def test_input_order_does_not_change_result(self):
        movements = seasonal_movements(date(2027, 9, 10))
        self.assertEqual(assess(movements), assess(reversed(movements)))

    def test_lower_receipts_cannot_improve_cash(self):
        results = [assess([CashMovement("sale", date(2027, 9, 10), D(amount))])
                   for amount in ("30000", "45000", "60000")]
        self.assertEqual([r.cash_after_repayment for r in results],
                         [D("48000"), D("63000"), D("78000")])


if __name__ == "__main__":
    unittest.main()
