# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace
from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import Mock

from test_get_case import changed_snapshot, saved_fixture

from farmcredit.adapters.demo import load_demo_case, load_demo_evidence
from farmcredit.application.assess_saved_case import assess_cashflow
from farmcredit.application.get_case import CaseScope, InvalidCaseSnapshot
from farmcredit.application.saved_assessments import input_snapshot, make_snapshot
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress


class AssessSavedCaseTests(TestCase):
    def setUp(self):
        self.saved = saved_fixture()
        self.scope = CaseScope("7", self.saved.assessment_id, "FC-001", 1, date(2026, 10, 6))
        self.assumptions = StressAssumptions(Decimal("20"), Decimal("20"))

    def calculate(self, saved=None, assumptions=None):
        return assess_cashflow(
            self.scope, lambda key: saved or self.saved, assumptions or self.assumptions
        )

    def test_monthly_gap_is_visible_despite_final_surplus(self):
        loader = Mock(return_value=self.saved)
        result = assess_cashflow(self.scope, loader, self.assumptions)
        loader.assert_called_once_with(self.saved.assessment_id)
        baseline = result.comparison.baseline.cashflow
        self.assertEqual(baseline.cash_after_repayment, Decimal("40000"))
        self.assertEqual(baseline.shortfalls[0].on, date(2027, 8, 15))
        self.assertEqual(baseline.shortfalls[0].amount, Decimal("-3000"))
        self.assertEqual(len(result.comparison.scenarios), 3)
        self.assertEqual(result.issues, ())
        self.assertIsNone(result.error)

    def test_seasonal_case_does_not_require_monthly_coverage_confirmation(self):
        case, records = load_demo_case(), load_demo_evidence()
        snapshot = make_snapshot(
            input_snapshot(case, records, self.assumptions, "seasonal"),
            compare_stress(case, records, self.assumptions, as_of=self.scope.evidence_as_of),
        )
        result = self.calculate(replace(self.saved, snapshot_json=snapshot))
        self.assertEqual(result.issues, ())
        self.assertEqual(len(result.comparison.baseline.cashflow.repayments), 1)

    def test_stored_totals_are_not_trusted(self):
        altered = changed_snapshot(
            self.saved, lambda s: s["result"].update(cash_after_repayment="999999")
        )
        self.assertEqual(self.calculate(altered), self.calculate())

    def test_missing_or_conflicting_evidence_blocks_calculation(self):
        def conflict(s):
            row = s["inputs"]["evidence"][1]
            s["inputs"]["evidence"].append(
                {**row, "record_id": "conflict", "input": {**row["input"], "value": "999"}}
            )

        for change in (
            lambda s: s["inputs"]["evidence"].pop(0),
            conflict,
            lambda s: s["inputs"]["case"].update(opening_cash=None),
        ):
            result = self.calculate(changed_snapshot(self.saved, change))
            self.assertIsNone(result.comparison)
            self.assertTrue(result.issues)

    def test_retries_have_stable_ids_and_assumptions_change_identity(self):
        first = self.calculate()
        self.assertEqual(first, self.calculate())
        changed = self.calculate(assumptions=StressAssumptions(Decimal("40"), Decimal("20")))
        self.assertNotEqual(first.calculation_id, changed.calculation_id)
        self.assertEqual(first.comparison.baseline, changed.comparison.baseline)
        self.assertLess(
            changed.comparison.scenarios[0].cashflow.cash_after_repayment,
            first.comparison.scenarios[0].cashflow.cash_after_repayment,
        )
        self.assertNotEqual(
            first.calculation_id,
            assess_cashflow(
                replace(self.scope, evidence_as_of=date(2026, 10, 7)),
                lambda key: self.saved,
                self.assumptions,
            ).calculation_id,
        )

    def test_invalid_stress_scenario_is_explicit_not_a_success(self):
        result = self.calculate(assumptions=StressAssumptions(Decimal("20"), Decimal("100")))
        scenario = result.comparison.scenarios[-1]
        self.assertIsNone(scenario.cashflow)
        self.assertIn("exceed gross harvest", scenario.error)

    def test_policy_mismatch_and_caller_replacement_inputs_are_rejected(self):
        saved = changed_snapshot(self.saved, lambda s: s["inputs"].update(policy_version="future"))
        with self.assertRaises(InvalidCaseSnapshot):
            self.calculate(saved)
        with self.assertRaises(ValueError):
            self.calculate(assumptions={"opening_cash": "999999"})
        with self.assertRaises(PermissionError):
            self.calculate(replace(self.saved, version=2))

    def test_invalid_saved_terms_return_failure_without_findings(self):
        def change(s):
            s["inputs"]["case"]["financing"]["schedule_source"] = ""

        result = self.calculate(changed_snapshot(self.saved, change))
        self.assertIsNone(result.comparison)
        self.assertIn("source and version", result.error)
