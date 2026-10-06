# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest import TestCase

from farmcredit.adapters.demo import DEMO_RECORDED_ON, load_monthly_case, load_monthly_evidence
from farmcredit.application.assess_case import assess_case
from farmcredit.application.assess_evidence import assess_sourced_case
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress
from farmcredit.domain.cashflow import CashMovement, assess_cashflow, assess_schedule

D = Decimal


class RepaymentScheduleTests(TestCase):
    def test_monthly_case_retains_early_gap_despite_final_surplus(self):
        result = assess_case(load_monthly_case())
        self.assertEqual(
            [row.cash_after for row in result.repayments],
            list(map(D, ("27500", "21000", "8500", "2000", "-9500", "40000"))),
        )
        self.assertEqual(result.shortfalls[0].on, date(2027, 8, 15))
        self.assertEqual(result.shortfalls[0].amount, D("-3000"))
        self.assertEqual(result.repayments[4].cash_before, D("-5500"))
        self.assertEqual(sum(row.due for row in result.repayments), D("22000"))

    def test_regular_income_covers_each_payment(self):
        result = assess_schedule(
            starts_on=date(2027, 1, 1),
            opening_cash=D("0"),
            movements=tuple(
                CashMovement(f"income-{m}", date(2027, m, 10), D("6000")) for m in range(1, 4)
            ),
            repayments=tuple(
                CashMovement(f"due-{m}", date(2027, m, 28), D("-4000")) for m in range(1, 4)
            ),
        )
        self.assertEqual(
            [r.cash_after for r in result.repayments], [D("2000"), D("4000"), D("6000")]
        )
        self.assertFalse(result.shortfalls)

    def test_one_payment_is_identical_to_existing_entry_point(self):
        repayment = CashMovement("due", date(2027, 2, 28), D("-100"))
        inputs = dict(starts_on=date(2027, 1, 1), opening_cash=D("200"), movements=())
        self.assertEqual(
            assess_cashflow(**inputs, repayment=repayment),
            assess_schedule(**inputs, repayments=(repayment,)),
        )

    def test_same_day_instalments_group_after_other_obligations(self):
        result = assess_schedule(
            starts_on=date(2027, 1, 1),
            opening_cash=D("100"),
            movements=(CashMovement("expense", date(2027, 1, 28), D("-10")),),
            repayments=(
                CashMovement("a", date(2027, 1, 28), D("-30")),
                CashMovement("b", date(2027, 1, 28), D("-40")),
            ),
        )
        self.assertEqual(len(result.repayments), 1)
        self.assertEqual(result.repayments[0].due, D("70"))
        self.assertEqual(result.repayments[0].cash_before, D("90"))
        self.assertEqual(result.repayments[0].cash_after, D("20"))

    def test_late_receipt_cannot_cover_instalments(self):
        case = load_monthly_case()
        result = assess_case(replace(case, sale=replace(case.sale, received_on=date(2027, 10, 15))))
        self.assertEqual(result.cash_after_repayment, D("-20000"))
        self.assertEqual(result.future_movements[0].amount, D("60000"))

    def test_missing_household_coverage_blocks_complete_result(self):
        for coverage in (None, date(2027, 8, 31)):
            with self.subTest(coverage=coverage), self.assertRaisesRegex(ValueError, "coverage"):
                assess_case(replace(load_monthly_case(), coverage_through=coverage))

    def test_invalid_schedule_terms_are_rejected(self):
        case = load_monthly_case()
        original = case.financing
        for financing in (
            replace(original, schedule=()),
            replace(original, schedule_source=""),
            replace(original, schedule_version=""),
            replace(original, schedule=original.schedule[:-1]),
            replace(
                original,
                schedule=(replace(original.schedule[0], amount=D("-3999")), *original.schedule[1:]),
            ),
            replace(
                original,
                schedule=(
                    replace(original.schedule[0], on=date(2027, 4, 1)),
                    *original.schedule[1:],
                ),
            ),
        ):
            with self.subTest(financing=financing), self.assertRaises(ValueError):
                assess_case(replace(case, financing=financing))

    def test_invalid_cashflow_schedules_are_rejected(self):
        due = CashMovement("due", date(2027, 2, 28), D("-10"))
        for schedule in (
            (),
            (due, due),
            (replace(due, amount=D("0")),),
            (replace(due, on=date(2026, 12, 31)),),
        ):
            with self.subTest(schedule=schedule), self.assertRaises(ValueError):
                assess_schedule(
                    starts_on=date(2027, 1, 1),
                    opening_cash=D("0"),
                    movements=(),
                    repayments=schedule,
                )

    def test_duplicate_between_schedule_and_ledger_is_rejected(self):
        case = load_monthly_case()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_case(
                replace(case, other_movements=(*case.other_movements, case.financing.schedule[0]))
            )

    def test_schedule_order_does_not_change_results(self):
        case = load_monthly_case()
        financing = replace(case.financing, schedule=reversed(case.financing.schedule))
        self.assertEqual(assess_case(case), assess_case(replace(case, financing=financing)))

    def test_same_day_receipt_requires_clarification(self):
        case = load_monthly_case()
        with self.assertRaisesRegex(ValueError, "ordering"):
            assess_case(replace(case, sale=replace(case.sale, received_on=date(2027, 9, 28))))

    def test_schedule_evidence_is_required_and_value_bound(self):
        case, records = load_monthly_case(), load_monthly_evidence()
        field = "repayment/instalment-4/amount"
        for evidence in (
            tuple(r for r in records if r.input.field != field),
            tuple(
                replace(r, input=replace(r.input, value=D("-3000")))
                if r.input.field == field
                else r
                for r in records
            ),
            tuple(r for r in records if r.input.field != "coverage_through"),
        ):
            result = assess_sourced_case(case, evidence, as_of=DEMO_RECORDED_ON)
            self.assertIsNone(result.cashflow)
            self.assertTrue(result.issues)

    def test_stress_reuses_all_instalments_and_retains_sources(self):
        records = load_monthly_evidence()
        comparison = compare_stress(
            load_monthly_case(),
            records,
            StressAssumptions(D("20"), D("20")),
            as_of=DEMO_RECORDED_ON,
        )
        self.assertEqual(comparison.baseline.records, records)
        self.assertEqual(
            [r.cashflow.cash_after_repayment for r in comparison.scenarios],
            [D("28000"), D("24000"), D("15200")],
        )
        for scenario in comparison.scenarios:
            self.assertEqual(len(scenario.cashflow.repayments), 6)
            self.assertEqual(scenario.cashflow.shortfalls[0].on, date(2027, 8, 15))

    def test_package_cannot_be_charged_again_beside_instalments(self):
        case = load_monthly_case()
        duplicate = CashMovement(case.financing.record_id, date(2027, 4, 10), D("-20000"))
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            assess_case(replace(case, other_movements=(*case.other_movements, duplicate)))
