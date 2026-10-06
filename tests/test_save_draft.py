# SPDX-License-Identifier: AGPL-3.0-only
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, connection, connections
from django.test import TransactionTestCase
from test_get_case import changed_snapshot, saved_fixture

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.adapters.case_reader import bind_case_reader
from farmcredit.adapters.draft_store import save_draft
from farmcredit.adapters.persistence.models import Draft, Review
from farmcredit.application.save_draft import CitedStatement, DraftRequest
from farmcredit.application.stress_scenarios import StressAssumptions


class SaveDraftTests(TransactionTestCase):
    def setUp(self):
        model = get_user_model()
        self.officer = model.objects.create_user("drafter", first_name="Demo Officer")
        permission, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(model),
            codename="review_assessment",
            defaults={"name": "Can review advisory"},
        )
        self.officer.user_permissions.add(permission)
        self.store = AssessmentStore()
        self.saved = self.store.save(saved_fixture().snapshot_json, str(uuid4()))
        self.store.record_current_inputs("FC-001", self.saved.snapshot["input_fingerprint"])
        self.reader = bind_case_reader(
            officer_id=str(self.officer.pk), assessment_id=self.saved.assessment_id
        )
        self.assumptions = StressAssumptions(Decimal("20"), Decimal("20"))
        calculation = self.reader.assess_cashflow(self.assumptions)
        source = self.reader.get_case().sources[0]
        self.request = DraftRequest(
            str(uuid4()),
            calculation.calculation_id,
            self.assumptions,
            (CitedStatement("Review the recorded start date.", (source.record_id,)),),
            (),
        )

    def test_save_attaches_authoritative_results_and_never_approves(self):
        saved = save_draft(self.reader, self.request)
        snapshot = json.loads(saved.snapshot_json)
        self.assertEqual(snapshot["status"], "draft")
        self.assertEqual(snapshot["kind"], "advisory")
        self.assertEqual(
            snapshot["calculation"]["comparison"]["baseline"]["cashflow"]["cash_after_repayment"],
            "40000",
        )
        self.assertEqual(snapshot["input_fingerprint"], self.saved.snapshot["input_fingerprint"])
        self.assertEqual(Review.objects.count(), 0)
        self.assertEqual(Draft.objects.get().officer_id, self.officer.pk)

    def test_retry_is_identical_even_after_inputs_change_but_changed_payload_fails(self):
        first = save_draft(self.reader, self.request)
        self.store.record_current_inputs("FC-001", "changed")
        self.assertEqual(save_draft(self.reader, self.request), first)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            save_draft(self.reader, replace(self.request, questions=("Changed question?",)))
        self.assertEqual(Draft.objects.count(), 1)

    def test_new_drafts_are_versioned_and_old_ones_immutable(self):
        first = save_draft(self.reader, self.request)
        second = save_draft(self.reader, replace(self.request, operation_id=str(uuid4())))
        self.assertEqual((first.version, second.version), (1, 2))
        with connection.cursor() as cursor:
            for sql in (
                "UPDATE persistence_draft SET version = 99",
                "DELETE FROM persistence_draft",
            ):
                with self.assertRaisesRegex(IntegrityError, "immutable"):
                    cursor.execute(sql)

    def test_stale_inputs_or_newer_saved_version_reject_new_drafts(self):
        self.store.record_current_inputs("FC-001", "changed")
        with self.assertRaisesRegex(ValueError, "Inputs have changed"):
            save_draft(self.reader, self.request)
        self.store.record_current_inputs("FC-001", self.saved.snapshot["input_fingerprint"])
        self.store.save(self.saved.snapshot_json, str(uuid4()))
        with self.assertRaisesRegex(ValueError, "Inputs have changed"):
            save_draft(self.reader, self.request)
        self.assertFalse(Draft.objects.exists())

    def test_foreign_citation_or_calculation_cannot_be_attached(self):
        for request in (
            replace(self.request, calculation_id="invented"),
            replace(self.request, calculation_id=None),
            replace(self.request, assumptions=StressAssumptions(Decimal("50"), Decimal("20"))),
            replace(self.request, statements=(CitedStatement("Claim", ("foreign-source",)),)),
        ):
            with self.assertRaises(ValueError):
                save_draft(self.reader, request)
        self.assertFalse(Draft.objects.exists())

    def test_revocation_blocks_new_saves_and_retries(self):
        save_draft(self.reader, self.request)
        self.officer.user_permissions.clear()
        with self.assertRaises(PermissionError):
            save_draft(self.reader, self.request)
        self.assertEqual(Draft.objects.count(), 1)

    def test_incomplete_evidence_requires_questions_and_preserves_gaps(self):
        incomplete = changed_snapshot(self.saved, lambda s: s["inputs"].update(evidence=[]))
        saved = self.store.save(incomplete.snapshot_json, str(uuid4()))
        self.store.record_current_inputs("FC-001", saved.snapshot["input_fingerprint"])
        reader = bind_case_reader(
            officer_id=str(self.officer.pk), assessment_id=saved.assessment_id
        )
        request = DraftRequest(
            str(uuid4()), None, self.assumptions, (), ("Supply dated source records.",)
        )
        result = json.loads(save_draft(reader, request).snapshot_json)
        self.assertEqual(result["kind"], "evidence_request")
        self.assertTrue(result["calculation"]["issues"])
        self.assertIsNone(result["calculation"]["comparison"])

    def test_empty_or_uncited_content_is_rejected(self):
        for kwargs in (
            {"statements": (), "questions": ()},
            {"statements": (CitedStatement("Claim", ()),)},
            {"questions": ("",)},
            {"operation_id": " "},
        ):
            with self.assertRaises(ValueError):
                replace(self.request, **kwargs)

    def test_concurrent_retries_create_one_draft(self):
        def save(_):
            try:
                return save_draft(self.reader, self.request)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(Draft.objects.count(), 1)

    def test_concurrent_new_drafts_receive_distinct_versions(self):
        def save(_):
            try:
                return save_draft(self.reader, replace(self.request, operation_id=str(uuid4())))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(sorted(r.version for r in results), [1, 2])
