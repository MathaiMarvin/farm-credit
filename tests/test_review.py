# SPDX-License-Identifier: AGPL-3.0-only
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from uuid import uuid4

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.domain.review import Officer, ReviewRequest, validate_review


class ReviewTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store = AssessmentStore(Path(self.directory.name) / "review.sqlite3")
        self.saved = self.store.save(
            '{"case_id":"FC-001","input_fingerprint":"original","inputs":{"policy_version":"cashflow-schedules-v1"}}',
            str(uuid4()),
        )
        revision = self.store.record_current_inputs("FC-001", "original")
        self.request = ReviewRequest(
            self.saved.assessment_id,
            str(uuid4()),
            revision,
            "approved",
            "Reviewed cash gaps.",
            Officer("7", "Demo Officer", True),
        )

    def test_review_binds_identity_version_and_preserves_retry(self):
        first = self.store.review(self.request)
        self.assertEqual(first, self.store.review(self.request))
        self.assertEqual(first.officer_name, "Demo Officer")
        self.assertEqual(first.assessment_id, self.saved.assessment_id)
        self.assertTrue(self.store.review_context(self.saved.assessment_id)["review_current"])

    def test_input_change_makes_approval_historical_even_if_later_restored(self):
        self.store.review(self.request)
        self.store.record_current_inputs("FC-001", "changed")
        self.assertFalse(self.store.review_context(self.saved.assessment_id)["review_current"])
        self.store.record_current_inputs("FC-001", "original")
        self.assertFalse(self.store.review_context(self.saved.assessment_id)["review_current"])

    def test_changed_inputs_and_obsolete_form_reject_approval(self):
        self.store.record_current_inputs("FC-001", "changed")
        with self.assertRaisesRegex(ValueError, "stale"):
            self.store.review(self.request)
        self.store.record_current_inputs("FC-001", "original")
        with self.assertRaisesRegex(ValueError, "changed while"):
            self.store.review(self.request)

    def test_newer_saved_version_prevents_review_of_old_version(self):
        self.store.save(self.saved.snapshot_json, str(uuid4()))
        with self.assertRaisesRegex(ValueError, "stale"):
            self.store.review(self.request)

    def test_missing_or_invalid_case_state_prevents_review(self):
        self.store.record_current_inputs("FC-001", None)
        with self.assertRaisesRegex(ValueError, "stale"):
            self.store.review(self.request)

    def test_change_request_needs_reason_and_new_version(self):
        with self.assertRaisesRegex(ValueError, "reason"):
            self.store.review(replace(self.request, decision="changes_requested", note=""))
        reviewed = self.store.review(
            replace(
                self.request,
                decision="changes_requested",
                note="Confirm outside debts.",
            )
        )
        self.assertEqual(reviewed.decision, "changes_requested")
        with self.assertRaisesRegex(ValueError, "already"):
            self.store.review(replace(self.request, operation_id=str(uuid4())))

    def test_named_authorised_officer_is_required(self):
        for officer in (
            Officer("7", "", True),
            Officer("7", "Name", False),
            Officer("", "Name", True),
        ):
            with self.subTest(officer=officer), self.assertRaisesRegex(ValueError, "officer"):
                self.store.review(replace(self.request, officer=officer))

    def test_concurrent_identical_review_is_idempotent(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.store.review(self.request), range(2)))
        self.assertEqual(results[0], results[1])

    def test_conflicting_retry_and_database_mutation_are_rejected(self):
        self.store.review(self.request)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.store.review(replace(self.request, decision="changes_requested"))
        with sqlite3.connect(self.store.path) as connection:
            for statement in (
                "DELETE FROM advisory_reviews",
                "UPDATE advisory_reviews SET note='x'",
            ):
                with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                    connection.execute(statement)

    def test_invalid_decision_and_excessive_note(self):
        for request in (
            replace(self.request, decision="loan_approved"),
            replace(self.request, note="x" * 2001),
        ):
            with self.assertRaises(ValueError):
                validate_review(
                    request,
                    latest=True,
                    saved_fingerprint="original",
                    current_fingerprint="original",
                    current_revision=1,
                    already_reviewed=False,
                )

    def test_policy_change_blocks_review_even_without_an_input_submission(self):
        from unittest.mock import patch

        with patch("farmcredit.adapters.assessment_store.POLICY_VERSION", "new-policy"):
            self.assertFalse(self.store.review_context(self.saved.assessment_id)["current"])
            with self.assertRaisesRegex(ValueError, "stale"):
                self.store.review(self.request)

    def test_concurrent_conflicting_decisions_preserve_only_one(self):
        requests = [
            self.request,
            replace(
                self.request,
                operation_id=str(uuid4()),
                decision="changes_requested",
                note="Please verify obligations.",
            ),
        ]

        def submit(request):
            try:
                return self.store.review(request)
            except ValueError:
                return None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, requests))
        self.assertEqual(sum(result is not None for result in results), 1)
