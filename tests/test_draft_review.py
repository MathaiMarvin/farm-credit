# SPDX-License-Identifier: AGPL-3.0-only
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import test_save_draft as fixtures
from django.contrib.auth import get_user_model
from django.core import signing
from django.db import IntegrityError, OperationalError, connection, connections
from django.test import Client, TransactionTestCase, override_settings

from farmcredit.adapters.draft_reviews import draft_context, review_draft
from farmcredit.adapters.draft_store import save_draft
from farmcredit.adapters.persistence.models import DraftReview, Review
from farmcredit.application.save_draft import CitedStatement
from farmcredit.domain.draft_review import DraftReviewRequest
from farmcredit.domain.review import Officer


@override_settings(ALLOWED_HOSTS=["testserver"])
class DraftReviewTests(TransactionTestCase):
    def setUp(self):
        fixtures.SaveDraftTests.setUp(self)
        self.draft = save_draft(self.reader, self.request)
        self.review = DraftReviewRequest(
            self.draft.draft_id,
            str(uuid4()),
            draft_context(self.draft.draft_id, str(self.officer.pk))["revision"],
            "approved",
            "Sources checked.",
            Officer(str(self.officer.pk), "Untrusted name", True),
        )
        self.client.force_login(self.officer)
        self.url = f"/drafts/{self.draft.draft_id}/"

    def form(self):
        return self.client.get(self.url).context["review_token"]

    def test_named_decision_preserves_draft_and_does_not_approve_assessment(self):
        result = review_draft(self.review)
        page = self.client.get(self.url)
        self.assertContains(page, "Lending decision")
        self.assertContains(page, "Not recorded here")
        self.assertContains(page, "Your review has been saved")
        self.assertEqual(result.officer_name, "Demo Officer")
        self.assertEqual(result.draft.snapshot_json, self.draft.snapshot_json)
        self.assertFalse(Review.objects.exists())
        self.assertTrue(draft_context(self.draft.draft_id, str(self.officer.pk))["review_current"])
        self.assertEqual(review_draft(self.review).pk, result.pk)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            review_draft(replace(self.review, decision="changes_requested"))
        with self.assertRaisesRegex(ValueError, "already been reviewed"):
            review_draft(replace(self.review, operation_id=str(uuid4())))

    def test_new_draft_makes_earlier_decision_historical(self):
        review_draft(self.review)
        save_draft(self.reader, replace(self.request, operation_id=str(uuid4())))
        context = draft_context(self.draft.draft_id, str(self.officer.pk))
        self.assertFalse(context["current"])
        self.assertFalse(context["review_current"])
        page = self.client.get(self.url)
        self.assertContains(page, "decision is historical")
        self.assertNotContains(page, "review_token")

    def test_newer_draft_blocks_an_open_review_form(self):
        token = self.form()
        save_draft(self.reader, replace(self.request, operation_id=str(uuid4())))
        response = self.client.post(
            self.url + "review/", {"review_token": token, "decision": "approved"}
        )
        self.assertEqual(response.status_code, 409)
        self.assertFalse(DraftReview.objects.exists())

    def test_case_change_and_revert_does_not_restore_current_review(self):
        self.store.record_current_inputs("FC-001", "changed")
        self.store.record_current_inputs("FC-001", self.saved.snapshot["input_fingerprint"])
        with self.assertRaisesRegex(ValueError, "historical"):
            review_draft(self.review)
        self.assertFalse(draft_context(self.draft.draft_id, str(self.officer.pk))["current"])

    def test_new_saved_assessment_and_policy_change_block_review(self):
        with patch("farmcredit.adapters.draft_reviews.POLICY_VERSION", "next-policy"):
            with self.assertRaisesRegex(ValueError, "historical"):
                review_draft(self.review)
        self.store.save(self.saved.snapshot_json, str(uuid4()))
        with self.assertRaisesRegex(ValueError, "historical"):
            review_draft(self.review)

    def test_permission_revocation_blocks_page_review_and_retry(self):
        review_draft(self.review)
        self.officer.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        with self.assertRaises(PermissionError):
            review_draft(self.review)

    def test_unnamed_or_inactive_officer_cannot_review(self):
        self.officer.first_name = ""
        self.officer.save()
        with self.assertRaises(PermissionError):
            review_draft(self.review)
        self.officer.first_name = "Demo Officer"
        self.officer.is_active = False
        self.officer.save()
        with self.assertRaises(PermissionError):
            review_draft(self.review)

    def test_review_form_validation_preserves_note_and_no_decision(self):
        token = self.form()
        response = self.client.post(
            self.url + "review/",
            {"review_token": token, "decision": "changes_requested", "note": ""},
        )
        self.assertContains(response, "Requests for changes need a reason", status_code=409)
        response = self.client.post(
            self.url + "review/",
            {
                "review_token": token,
                "decision": "invalid",
                "note": "Please verify the dated sources.",
            },
        )
        self.assertContains(response, "Please verify the dated sources.", status_code=409)
        self.assertFalse(DraftReview.objects.exists())
        response = self.client.post(
            self.url + "review/",
            {"review_token": token, "decision": "changes_requested", "note": "Verify the dates."},
            follow=True,
        )
        self.assertContains(response, "Changes requested")
        self.assertContains(response, "Verify the dates.")

    def test_signed_form_binds_officer_draft_and_expiry(self):
        token = self.form()
        another = save_draft(self.reader, replace(self.request, operation_id=str(uuid4())))
        response = self.client.post(
            f"/drafts/{another.draft_id}/review/", {"review_token": token, "decision": "approved"}
        )
        self.assertEqual(response.status_code, 400)
        other = get_user_model().objects.create_user("another-reviewer", first_name="Other Officer")
        other.user_permissions.set(self.officer.user_permissions.all())
        self.client.force_login(other)
        self.assertEqual(
            self.client.post(
                self.url + "review/", {"review_token": token, "decision": "approved"}
            ).status_code,
            400,
        )
        self.client.force_login(self.officer)
        payload = signing.loads(token, salt="draft-review")
        with patch("django.core.signing.time.time", return_value=0):
            expired = signing.dumps(payload, salt="draft-review")
        self.assertEqual(
            self.client.post(
                self.url + "review/", {"review_token": expired, "decision": "approved"}
            ).status_code,
            400,
        )
        self.assertFalse(DraftReview.objects.exists())

    def test_anonymous_csrf_and_post_boundaries(self):
        anonymous = Client()
        self.assertEqual(anonymous.get(self.url).status_code, 302)
        response = anonymous.post(self.url + "review/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/accounts/login/?next=" + self.url)
        response = anonymous.post(self.url + "review/", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertIn(self.url, response["HX-Redirect"])
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.officer)
        self.assertEqual(csrf_client.post(self.url + "review/").status_code, 403)
        self.assertEqual(self.client.get(self.url + "review/").status_code, 405)

    def test_narrative_sources_and_notes_are_escaped(self):
        request = replace(
            self.request,
            operation_id=str(uuid4()),
            statements=(
                CitedStatement("<script>alert(1)</script>", self.request.statements[0].record_ids),
            ),
        )
        another = save_draft(self.reader, request)
        response = self.client.get(f"/drafts/{another.draft_id}/")
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")
        self.assertContains(response, 'href="#source-1"')

    def test_assessment_links_to_draft_and_page_shows_early_gap(self):
        response = self.client.get(f"/assessments/{self.saved.assessment_id}/")
        self.assertContains(response, self.url)
        self.assertNotContains(response, "Approve advisory v1")
        response = self.client.get(self.url)
        self.assertContains(response, "2027-08-15")
        self.assertContains(response, "-3,000.00")
        self.assertContains(response, "40,000.00")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(self.client.get("/drafts/missing/").status_code, 404)

    def test_evidence_request_review_has_explicit_meaning(self):
        from test_get_case import changed_snapshot

        from farmcredit.adapters.case_reader import bind_case_reader
        from farmcredit.application.save_draft import DraftRequest

        incomplete = changed_snapshot(self.saved, lambda s: s["inputs"].update(evidence=[]))
        saved = self.store.save(incomplete.snapshot_json, str(uuid4()))
        self.store.record_current_inputs("FC-001", saved.snapshot["input_fingerprint"])
        reader = bind_case_reader(
            officer_id=str(self.officer.pk), assessment_id=saved.assessment_id
        )
        draft = save_draft(
            reader,
            DraftRequest(
                str(uuid4()), None, self.assumptions, (), ("Supply dated source records.",)
            ),
        )
        response = self.client.get(f"/drafts/{draft.draft_id}/")
        self.assertContains(response, "Approve evidence request")
        self.assertContains(response, "More evidence or clarification needed")
        self.assertNotContains(response, "No shortfall under these assumptions")

    def test_storage_failure_never_claims_review_succeeded(self):
        token = self.form()
        with patch(
            "farmcredit.interfaces.web.draft_views.review_draft", side_effect=OperationalError
        ):
            response = self.client.post(
                self.url + "review/",
                {"review_token": token, "decision": "approved", "note": "Keep this note."},
            )
        self.assertContains(response, "could not be confirmed", status_code=503)
        self.assertContains(response, "Keep this note.", status_code=503)
        self.assertFalse(DraftReview.objects.exists())

    def test_database_rejects_mutation_and_concurrent_retries_make_one_decision(self):
        def save(_):
            try:
                return review_draft(self.review).pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(DraftReview.objects.count(), 1)
        with connection.cursor() as cursor:
            for statement in (
                "UPDATE persistence_draftreview SET note = 'changed'",
                "DELETE FROM persistence_draftreview",
            ):
                with self.assertRaisesRegex(IntegrityError, "immutable"):
                    cursor.execute(statement)
        self.assertEqual(json.loads(self.draft.snapshot_json)["status"], "draft")
