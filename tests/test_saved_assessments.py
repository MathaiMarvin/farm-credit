# SPDX-License-Identifier: AGPL-3.0-only
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, connection, connections
from django.test import TransactionTestCase

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.adapters.demo import DEMO_RECORDED_ON, load_monthly_case, load_monthly_evidence
from farmcredit.application.saved_assessments import (
    input_fingerprint,
    input_snapshot,
    make_snapshot,
)
from farmcredit.application.stress_scenarios import StressAssumptions, compare_stress


class SavedAssessmentTests(TransactionTestCase):
    def setUp(self):
        self.store = AssessmentStore()
        self.case, self.records = load_monthly_case(), load_monthly_evidence()
        self.assumptions = StressAssumptions(Decimal("20"), Decimal("20"))
        self.inputs = input_snapshot(self.case, self.records, self.assumptions, "monthly")
        self.comparison = compare_stress(
            self.case,
            self.records,
            self.assumptions,
            as_of=DEMO_RECORDED_ON,
        )
        self.payload = make_snapshot(self.inputs, self.comparison)

    def test_reopen_preserves_exact_inputs_evidence_and_results(self):
        saved = self.store.save(self.payload, str(uuid4()))
        reopened = AssessmentStore().get(saved.assessment_id)
        self.assertEqual(saved, reopened)
        self.assertEqual(reopened.snapshot["inputs"], self.inputs)
        self.assertEqual(reopened.snapshot["result"]["cash_after_repayment"], "40000")
        self.assertEqual(len(reopened.snapshot["result"]["repayments"]), 6)
        self.assertEqual(len(reopened.snapshot["inputs"]["evidence"]), 47)
        self.assertEqual(len(reopened.snapshot["scenarios"]), 3)
        mutable_copy = reopened.snapshot
        mutable_copy["inputs"].clear()
        self.assertEqual(reopened.snapshot["inputs"], self.inputs)

    def test_retried_save_returns_same_version(self):
        operation = str(uuid4())
        first = self.store.save(self.payload, operation)
        self.assertEqual(first, self.store.save(self.payload, operation))
        self.assertEqual(len(self.store.history("FC-001")), 1)

    def test_concurrent_retry_cannot_duplicate_version(self):
        operation = str(uuid4())

        def save(_):
            try:
                return self.store.save(self.payload, operation)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(save, range(2)))
        self.assertEqual(saved[0], saved[1])
        self.assertEqual(len(self.store.history("FC-001")), 1)

    def test_conflicting_retry_is_rejected_without_overwrite(self):
        operation = str(uuid4())
        self.store.save(self.payload, operation)
        with self.assertRaisesRegex(ValueError, "different snapshot"):
            self.store.save(self.payload.replace('"40000"', '"40001"'), operation)
        self.assertEqual(self.store.get(operation).snapshot_json, self.payload)

    def test_new_operation_creates_new_version_and_history_is_newest_first(self):
        first = self.store.save(self.payload, str(uuid4()))
        second = self.store.save(self.payload, str(uuid4()))
        self.assertEqual([r.version for r in self.store.history("FC-001")], [2, 1])
        self.assertEqual(self.store.get(first.assessment_id), first)
        self.assertNotEqual(first.assessment_id, second.assessment_id)

    def test_database_rejects_update_and_delete(self):
        self.store.save(self.payload, str(uuid4()))
        with connection.cursor() as cursor:
            for statement in (
                "UPDATE persistence_assessment SET version = 99",
                "DELETE FROM persistence_assessment",
            ):
                with self.assertRaisesRegex(IntegrityError, "immutable"):
                    cursor.execute(statement)

    def test_fingerprint_detects_input_source_stress_and_policy_changes(self):
        baseline = input_fingerprint(self.inputs)
        variations = [
            input_snapshot(
                replace(self.case, opening_cash=Decimal("39999")),
                self.records,
                self.assumptions,
                "monthly",
            ),
            input_snapshot(
                self.case,
                (replace(self.records[0], source="Changed source"), *self.records[1:]),
                self.assumptions,
                "monthly",
            ),
            input_snapshot(
                self.case, self.records, StressAssumptions(Decimal("21"), Decimal("20")), "monthly"
            ),
            {**self.inputs, "policy_version": "changed"},
        ]
        for inputs in variations:
            self.assertNotEqual(baseline, input_fingerprint(inputs))

    def test_decimal_formatting_does_not_create_false_staleness(self):
        equivalent = input_snapshot(
            replace(self.case, opening_cash=Decimal("40000.00")),
            self.records,
            self.assumptions,
            "monthly",
        )
        self.assertEqual(input_fingerprint(self.inputs), input_fingerprint(equivalent))

    def test_incomplete_calculation_cannot_be_snapshotted(self):
        blocked = compare_stress(self.case, (), self.assumptions, as_of=DEMO_RECORDED_ON)
        with self.assertRaisesRegex(ValueError, "completed"):
            make_snapshot(self.inputs, blocked)

    def test_unknown_id(self):
        self.assertIsNone(self.store.get(str(uuid4())))

    def test_concurrent_new_saves_receive_distinct_versions(self):
        def save(_):
            try:
                return self.store.save(self.payload, str(uuid4()))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            saved = list(pool.map(save, range(2)))
        self.assertEqual(sorted(item.version for item in saved), [1, 2])
