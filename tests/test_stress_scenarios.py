# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from farmcredit.adapters.demo import DEMO_RECORDED_ON, load_demo_case, load_demo_evidence
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress


class StressTests(TestCase):
    def compare(self, price="20", harvest="20", case=None, records=None):
        return compare_stress(
            case or load_demo_case(),
            load_demo_evidence() if records is None else records,
            StressAssumptions(Decimal(price), Decimal(harvest)),
            as_of=DEMO_RECORDED_ON,
        )

    def test_exact_comparison_and_unchanged_sources(self):
        case, records = load_demo_case(), load_demo_evidence()
        comparison = self.compare(case=case, records=records)
        self.assertEqual(comparison.baseline.cashflow.cash_after_repayment, Decimal("40000"))
        self.assertEqual(
            [item.cashflow.cash_after_repayment for item in comparison.scenarios],
            [Decimal("28000"), Decimal("24000"), Decimal("15200")],
        )
        self.assertEqual(comparison.baseline.records, records)
        self.assertEqual(case, load_demo_case())
        for item in comparison.scenarios:
            self.assertEqual(item.case.sale.retained_kg, case.sale.retained_kg)
            self.assertEqual(item.case.sale.lost_kg, case.sale.lost_kg)
            self.assertEqual(item.case.other_movements, case.other_movements)

    def test_zero_reductions_match_baseline(self):
        comparison = self.compare("0", "0")
        for item in comparison.scenarios:
            self.assertEqual(item.cashflow, comparison.baseline.cashflow)

    def test_impossible_harvest_blocks_only_affected_scenarios(self):
        comparison = self.compare(harvest="100")
        self.assertIsNotNone(comparison.scenarios[0].cashflow)
        for item in comparison.scenarios[1:]:
            self.assertIsNone(item.cashflow)
            self.assertIn("exceed gross harvest", item.error)
        self.assertIsNotNone(comparison.baseline.cashflow)

    def test_total_price_loss_and_combined_shortfalls(self):
        comparison = self.compare("100", "20")
        self.assertEqual(comparison.scenarios[0].cashflow.cash_after_repayment, Decimal("-20000"))
        comparison = self.compare("50", "50")
        self.assertEqual(comparison.scenarios[2].cashflow.cash_after_repayment, Decimal("-10000"))
        self.assertTrue(comparison.scenarios[2].cashflow.shortfalls)

    def test_missing_or_conflicting_evidence_never_runs_stress_calculator(self):
        records = load_demo_evidence()
        conflict = replace(
            records[1], record_id="conflict", input=replace(records[1].input, value=Decimal("1"))
        )
        for evidence in ((), (*records, conflict)):
            with patch("farmcredit.application.stress_scenarios.assess_case") as calculate:
                comparison = self.compare(records=evidence)
            calculate.assert_not_called()
            self.assertTrue(comparison.baseline.issues)
            self.assertEqual(comparison.scenarios, ())

    def test_reductions_cannot_increase_cash(self):
        for reduction in ("0", "0.01", "20", "50", "75"):
            comparison = self.compare(reduction, reduction)
            for scenario in comparison.scenarios:
                if scenario.cashflow:
                    self.assertLessEqual(
                        scenario.cashflow.cash_after_repayment,
                        comparison.baseline.cashflow.cash_after_repayment,
                    )

    def test_price_rounds_half_up_to_cents(self):
        comparison = self.compare("0.0125", "0")
        self.assertEqual(comparison.scenarios[0].case.sale.price_per_kg, Decimal("40.00"))

    def test_invalid_reductions_are_rejected(self):
        for value in (Decimal("-1"), Decimal("101"), Decimal("NaN"), Decimal("Infinity"), 20):
            with self.subTest(value=value), self.assertRaises(ValueError):
                StressAssumptions(value, Decimal("20"))

    def test_earlier_shortfalls_survive_a_positive_final_balance(self):
        case = replace(load_demo_case(), opening_cash=Decimal("30000"))
        records = tuple(
            replace(record, input=replace(record.input, value=Decimal("30000")))
            if record.input.field == "opening_cash"
            else record
            for record in load_demo_evidence()
        )
        comparison = self.compare("0", "0", case=case, records=records)
        for scenario in comparison.scenarios:
            self.assertGreater(scenario.cashflow.cash_after_repayment, 0)
            self.assertTrue(
                any(
                    balance.on < case.financing.repayment_on
                    for balance in scenario.cashflow.shortfalls
                )
            )

    def test_late_receipts_remain_excluded_in_every_stress_scenario(self):
        original = load_demo_case()
        receipt_date = date(2027, 10, 15)
        case = replace(original, sale=replace(original.sale, received_on=receipt_date))
        records = tuple(
            replace(record, input=replace(record.input, value=receipt_date))
            if record.input.field == "sale.received_on"
            else record
            for record in load_demo_evidence()
        )
        comparison = self.compare(case=case, records=records)
        for scenario in comparison.scenarios:
            self.assertEqual(scenario.cashflow.cash_after_repayment, Decimal("-20000"))
            self.assertEqual(scenario.cashflow.future_movements[0].on, receipt_date)
