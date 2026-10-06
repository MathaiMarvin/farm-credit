# SPDX-License-Identifier: AGPL-3.0-only
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase

from farmcredit.adapters.demo import load_demo_case
from farmcredit.adapters.institution_demo import (
    DEMO_REVIEW_POLICY,
    load_member_file,
    snapshot_institution,
)
from farmcredit.application.institution_evidence import (
    assess_institution,
    institution_sources,
    restore_institution,
)
from farmcredit.application.saved_assessments import input_fingerprint
from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.institution import (
    RepaymentRecord,
    ReviewPolicy,
    SavingsRecord,
    review_institution,
)

AS_OF = date(2026, 10, 6)


class InstitutionDomainTests(TestCase):
    def setUp(self):
        self.file = load_member_file("DEMO-001")
        self.case = load_demo_case()

    def review(self, file=None, movements=None, policy=None):
        return review_institution(
            file or self.file,
            policy or DEMO_REVIEW_POLICY,
            as_of=AS_OF,
            starts_on=self.case.starts_on,
            ends_on=self.case.financing.repayment_on,
            movements=self.case.other_movements if movements is None else movements,
        )

    def test_complete_file_has_no_review_blockers_but_never_approves_credit(self):
        result = self.review()
        self.assertEqual(result.status, "checks_satisfied")
        self.assertEqual(result.arrears, Decimal(0))
        self.assertTrue(all(check.status == "satisfied" for check in result.checks))
        self.assertEqual(result.cashflow_issues, ())
        self.assertIn("lender retains", result.limitations[0])

    def test_arrears_are_exact_recorded_difference_and_require_review(self):
        result = self.review(load_member_file("DEMO-002"))
        self.assertEqual(result.arrears, Decimal("1500"))
        self.assertEqual(result.status, "officer_review")
        self.assertEqual(result.checks[1].record_ids, ("DEMO-002:repayment-2025",))
        self.assertEqual(result.cashflow_issues[0].field, "institution.arrears")

    def test_missing_history_never_becomes_clean_repayment_record(self):
        for history in (None, ()):
            result = self.review(replace(self.file, repayments=history))
            self.assertEqual(result.status, "evidence_required")
            self.assertIsNone(result.arrears)
            self.assertEqual(result.checks[0].status, "evidence_required")
            self.assertTrue(result.questions)

    def test_restricted_and_unrestricted_savings_are_not_cash_movements(self):
        original = self.case.other_movements
        result = self.review(
            replace(
                self.file,
                savings=SavingsRecord("large-balance", Decimal("1000000"), Decimal("900000")),
            )
        )
        self.assertEqual(result, self.review())
        self.assertEqual(self.case.other_movements, original)
        self.assertIn("not added", result.limitations[1])

    def test_missing_yield_and_savings_remain_explicit_unknowns(self):
        result = self.review(replace(self.file, yields=None, savings=None))
        self.assertEqual(result.status, "evidence_required")
        self.assertTrue(any("Historical yields" in q for q in result.questions))
        self.assertTrue(any("savings balance" in q for q in result.questions))

    def test_known_obligation_must_match_once_by_reference_date_and_amount(self):
        for movements in (
            tuple(m for m in self.case.other_movements if m.record_id != "existing-debt"),
            tuple(
                replace(m, amount=Decimal("-4000")) if m.record_id == "existing-debt" else m
                for m in self.case.other_movements
            ),
            (
                *self.case.other_movements,
                CashMovement("possible-duplicate", date(2027, 8, 15), Decimal("-5000")),
            ),
        ):
            result = self.review(movements=movements)
            self.assertTrue(result.cashflow_issues)
            self.assertEqual(result.checks[-1].status, "evidence_required")
        self.assertEqual(self.review().cashflow_issues, ())

    def test_zero_obligations_and_unknown_obligations_have_distinct_coverage(self):
        zero = replace(self.file, obligations=())
        missing = replace(self.file, obligations=None)
        self.assertEqual(self.review(zero).checks[-1].status, "satisfied")
        self.assertEqual(self.review(missing).checks[-1].status, "evidence_required")
        rows = institution_sources(zero, DEMO_REVIEW_POLICY, as_of=AS_OF)
        self.assertEqual(
            next(
                r.values["recorded_obligation_count"]
                for r in rows
                if r.category == "current_obligations"
            ),
            0,
        )
        self.assertFalse(
            any(
                r.category == "current_obligations"
                for r in institution_sources(missing, DEMO_REVIEW_POLICY, as_of=AS_OF)
            )
        )

    def test_overdue_obligation_needs_timing_and_later_obligation_stays_visible(self):
        obligation = self.file.obligations[0]
        earlier = replace(self.file, obligations=(replace(obligation, due_on=date(2027, 3, 1)),))
        self.assertIn("predates", self.review(earlier).cashflow_issues[0].reason)
        later = replace(self.file, obligations=(replace(obligation, due_on=date(2028, 1, 1)),))
        self.assertEqual(self.review(later).cashflow_issues, ())
        self.assertTrue(
            any(
                r.category == "current_obligations"
                for r in institution_sources(later, DEMO_REVIEW_POLICY, as_of=AS_OF)
            )
        )

    def test_supplied_policy_is_explicit_and_unsupported_rules_fail_closed(self):
        with self.assertRaises(ValueError):
            replace(DEMO_REVIEW_POLICY, rules=("approve_all_loans",))
        with self.assertRaises(ValueError):
            ReviewPolicy("", "v1", "source", AS_OF, ("repayment_history_required",))
        future = replace(DEMO_REVIEW_POLICY, effective_on=date(2026, 10, 7))
        self.assertEqual(self.review(policy=future).status, "evidence_required")
        self.assertEqual(self.review(policy=future).checks, ())

    def test_invalid_financial_records_are_not_accepted(self):
        for args in (
            ("s", Decimal("-1"), Decimal("0")),
            ("s", Decimal("1"), Decimal("2")),
            ("s", Decimal("NaN"), Decimal("0")),
        ):
            with self.assertRaises(ValueError):
                SavingsRecord(*args)
        with self.assertRaises(ValueError):
            RepaymentRecord("r", AS_OF, Decimal("1"), Decimal("2"))
        with self.assertRaises(ValueError):
            replace(self.file, repayments=(*self.file.repayments, *self.file.repayments))

    def test_snapshot_hash_and_member_binding_are_enforced(self):
        encoded = snapshot_institution(
            "DEMO-001", retrieved_at=datetime(2026, 10, 6, tzinfo=timezone.utc)
        )
        file, policy, _ = restore_institution(encoded, expected_member="DEMO-001")
        self.assertEqual(file, self.file)
        self.assertEqual(policy, DEMO_REVIEW_POLICY)
        with self.assertRaises(PermissionError):
            restore_institution(encoded, expected_member="DEMO-002")
        changed = json.loads(encoded)
        changed["file"]["savings"]["balance"] = "99999"
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            restore_institution(json.dumps(changed), expected_member="DEMO-001")

    def test_historical_review_does_not_expose_future_observations(self):
        from farmcredit.adapters.demo import load_demo_evidence
        from farmcredit.application.saved_assessments import input_snapshot
        from farmcredit.application.stress_scenarios import StressAssumptions

        inputs = input_snapshot(
            self.case,
            load_demo_evidence(),
            StressAssumptions(Decimal("20"), Decimal("20")),
            "seasonal",
        )
        inputs["institution_record_set"] = "DEMO-001"
        body = json.loads(
            snapshot_institution(
                "DEMO-001", retrieved_at=datetime(2026, 10, 6, tzinfo=timezone.utc)
            )
        )
        body["file"]["recorded_on"] = "2026-10-07"
        body["fingerprint"] = input_fingerprint({key: body[key] for key in ("file", "policy")})
        result = assess_institution(json.dumps(body), inputs, as_of=AS_OF)
        self.assertIsNone(result.file.savings)
        self.assertIsNone(result.file.repayments)
        self.assertIsNone(result.review.arrears)
        self.assertTrue(all(r.category == "lender_policy" for r in result.sources))
