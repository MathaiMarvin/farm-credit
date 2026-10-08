# SPDX-License-Identifier: AGPL-3.0-only
import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import test_applications as fixtures
from django.db import connections, transaction
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse

from farmcredit.adapters.agent_runs import start_run
from farmcredit.adapters.persistence.models import AgentRun, Draft, ToolCall
from farmcredit.adapters.run_progress import read_run_progress
from farmcredit.interfaces.web.walkthrough import (
    advisory_status,
    evidence_progress,
    progress_context,
    review_summary,
    statement_cards,
)


class SummaryTests(SimpleTestCase):
    def test_statement_links_remove_only_recognised_duplicate_markers(self):
        snapshot = {
            "sources": [{"record_id": "price:1"}],
            "statements": [
                {
                    "text": "Assumed price (record_id: price:1). Unverified (record_id: foreign).",
                    "record_ids": ["price:1"],
                }
            ],
        }
        card = statement_cards(snapshot)[0]
        self.assertEqual(card["text"], "Assumed price. Unverified (record_id: foreign).")
        self.assertEqual(card["citations"], [{"anchor": 1, "record_id": "price:1"}])
        self.assertIn("(record_id: price:1)", snapshot["statements"][0]["text"])

    def test_live_evidence_retains_missing_records_and_never_invents_success(self):
        calls = [
            {
                "tool": "get_records",
                "status": "succeeded",
                "arguments": {"categories": ["repayment_history", "weather"]},
                "result": {"groups": [{"category": "repayment_history", "status": "unavailable"}]},
            }
        ]
        self.assertEqual(
            [r["status"] for r in evidence_progress(calls)], ["Unavailable", "No result recorded"]
        )
        calls.append(
            {"tool": "get_records", "status": "running", "arguments": {"categories": ["weather"]}}
        )
        self.assertEqual(evidence_progress(calls)[1]["status"], "Checking")
        calls[-1]["status"] = "failed"
        self.assertEqual(evidence_progress(calls)[1]["status"], "Read failed")

    def test_readiness_does_not_hide_source_questions_behind_positive_cashflow(self):
        snapshot = {
            "institution": {"review": {"status": "checks_satisfied", "questions": []}},
            "calculation": {
                "comparison": {
                    "baseline": {
                        "cashflow": {"balances": [{"amount": "0"}], "cash_after_repayment": "0"}
                    }
                }
            },
            "weather": {"review": {"questions": ["Confirm seasonal coverage"]}},
        }
        result = review_summary(snapshot)["readiness"]
        self.assertEqual(result["clear"], 2)
        self.assertEqual(result["label"], "Further review needed")
        snapshot["weather"]["review"]["questions"] = []
        self.assertEqual(review_summary(snapshot)["readiness"]["clear"], 3)
        snapshot.pop("institution")
        self.assertEqual(
            review_summary(snapshot)["readiness"]["rows"][0]["status"], "Evidence needed"
        )

    def test_review_status_never_represents_advisory_acceptance_as_lending_approval(self):
        context = {
            "current": True,
            "review": None,
            "review_current": False,
            "snapshot": {"kind": "advisory"},
        }
        self.assertEqual(advisory_status(context)["label"], "Awaiting your review")
        context.update(review=SimpleNamespace(decision="approved"), review_current=True)
        self.assertEqual(advisory_status(context)["label"], "Advisory approved")
        context["snapshot"]["kind"] = "evidence_request"
        self.assertEqual(advisory_status(context)["label"], "Evidence request approved")
        context["review"].decision = "changes_requested"
        self.assertEqual(advisory_status(context)["label"], "Changes requested")
        context["current"] = False
        self.assertEqual(advisory_status(context)["label"], "Historical advisory")

    def test_open_questions_lead_even_when_cashflow_has_no_gap(self):
        snapshot = {
            "calculation": {
                "comparison": {
                    "baseline": {
                        "cashflow": {
                            "balances": [{"on": "2027-01-01", "amount": "0"}],
                            "cash_after_repayment": "0",
                        }
                    },
                    "scenarios": [],
                }
            },
            "questions": ["Obtain buyer quote"],
        }
        summary = review_summary(snapshot)
        self.assertEqual(summary["headline"], "1 question to resolve")
        self.assertEqual(summary["cash_after"], "0")
        self.assertEqual(summary["tone"], "attention")
        snapshot["questions"] = []
        self.assertEqual(review_summary(snapshot)["headline"], "Ready for an officer’s review")

    def test_live_status_does_not_duplicate_current_work_as_completed(self):
        run = {
            "status": "active",
            "calls": [
                {"tool": "get_case", "status": "succeeded"},
                {
                    "tool": "get_records",
                    "status": "running",
                    "arguments": {"categories": ["savings", "harvest"]},
                },
            ],
        }
        progress = progress_context(run)
        self.assertEqual(len(progress["recent_checks"]), 1)
        self.assertEqual(progress["recent_checks"][0]["label"], "Read saved application")
        self.assertIn("2 evidence categories", progress["progress_message"])
        self.assertEqual(progress["completed_checks"], 1)

    def test_progress_never_invents_a_tool_during_model_wait_or_after_timeout(self):
        run = {"status": "active", "calls": [], "last_event": "model_request"}
        waiting = progress_context(run)
        self.assertIn("Waiting for the agent", waiting["progress_heading"])
        self.assertEqual(waiting["activity"], [])
        self.assertEqual(waiting["completed_checks"], 0)
        run["timed_out"] = True
        timed_out = progress_context(run)
        self.assertFalse(timed_out["watch"])
        self.assertEqual(timed_out["progress_heading"], "Outcome not confirmed")
        self.assertFalse(progress_context({"status": "incomplete", "calls": []})["watch"])

    def test_unknown_and_zero_are_distinct_and_early_gap_is_visible(self):
        snapshot = {"calculation": {"comparison": None, "error": "Missing schedule"}}
        self.assertIsNone(review_summary(snapshot)["cash_after"])
        self.assertEqual(review_summary(snapshot)["questions"], ["Missing schedule"])
        snapshot["calculation"] = {
            "comparison": {
                "baseline": {
                    "cashflow": {
                        "cash_after_repayment": "0",
                        "balances": [
                            {"on": "2027-01-01", "amount": "-1"},
                            {"on": "2027-02-01", "amount": "0"},
                        ],
                    }
                },
                "scenarios": [{"label": "Invalid stress", "error": "Missing yield"}],
            }
        }
        result = review_summary(snapshot)
        self.assertEqual(result["cash_after"], "0")
        self.assertEqual(result["first_gap"]["amount"], "-1")
        self.assertEqual(result["title"], "Repayment terms need review")
        self.assertIsNone(result["scenarios"][0]["cash_after"])

    def test_source_questions_survive_model_omission_and_are_deduplicated(self):
        snapshot = {
            "calculation": {"comparison": None},
            "institution": {"review": {"questions": ["Obtain history"]}},
            "market": {"review": {"questions": ["Obtain buyer quote"]}},
            "weather": {"review": {"questions": ["Confirm season coverage"]}},
            "questions": ["Obtain history"],
        }
        self.assertEqual(
            review_summary(snapshot)["questions"],
            ["Obtain history", "Obtain buyer quote", "Confirm season coverage"],
        )


class WalkthroughTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save

    def test_saved_inventory_distinguishes_unknown_zero_and_supplied_assumptions(self):
        saved = self.save({**fixtures.intake_data(), "opening_cash": "0"})
        page = self.client.get(reverse("application-intake", args=[saved.application_id]))
        self.assertContains(page, "A saved case is enough to start")
        self.assertContains(page, "Institution file · Not linked")
        groups = page.context["evidence_inventory"]
        opening = next(
            f for f in groups[0]["facts"] if f["label"] == "Available opening cash (KSh)"
        )
        self.assertEqual(opening["value"], 0)
        self.assertEqual(groups[1]["status"], "Needs information")
        self.assertTrue(any(f["value"] is None for f in groups[1]["facts"]))

    def test_real_recorded_institution_outcomes_drive_readiness(self):
        for member, expected in (
            ("DEMO-001", "Clear in supplied file"),
            ("DEMO-002", "Officer review needed"),
            ("DEMO-003", "Evidence needed"),
        ):
            with self.subTest(member=member):
                saved = self.save(
                    {**fixtures.intake_data(complete=True), "institution_record_set": member}
                )
                details = fixtures.ApplicationTests.investigate(self, saved)
                snapshot = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
                summary = review_summary(snapshot)
                readiness = summary["readiness"]
                self.assertEqual(readiness["rows"][0]["status"], expected)
                if member != "DEMO-001":
                    self.assertLess(readiness["clear"], readiness["total"])
                    self.assertIsNone(summary["cash_after"])
                    self.assertEqual(readiness["label"], "Further review needed")
                page = self.client.get(reverse("saved-draft", args=[details["draft_id"]]))
                self.assertContains(page, "Evidence readiness")
                self.assertContains(page, expected)

    def test_signed_start_retry_reuses_run_and_forgery_cannot_start(self):
        saved = self.save()
        page = self.client.get(reverse("application-intake", args=[saved.application_id]))
        token = page.context["investigation_token"]
        run_id = page.context["run_id"]
        url = reverse("application-investigate", args=[saved.application_id])

        def launch(**kwargs):
            return start_run(**kwargs, model="test-scripted")

        with patch(
            "farmcredit.interfaces.web.application_views.investigate_application_with_model",
            side_effect=launch,
        ) as launch_mock:
            response = self.client.post(
                url, {"mode": "model", "investigation_token": token}, HTTP_HX_REQUEST="true"
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["HX-Redirect"], reverse("application-run", args=[run_id]))
            self.client.post(url, {"mode": "model", "investigation_token": token})
            self.assertEqual(launch_mock.call_count, 1)
            bad = self.client.post(
                url, {"mode": "model", "investigation_token": token + "x"}, HTTP_HX_REQUEST="true"
            )
            self.assertContains(bad, "expired or changed", status_code=409)
            self.assertEqual(launch_mock.call_count, 1)
        self.assertEqual(AgentRun.objects.count(), 1)

    def test_progress_reads_committed_activity_without_execution_lock(self):
        saved = self.save()
        run_id = start_run(
            application_id=saved.application_id, officer_id=self.officer_id, model="test-scripted"
        )
        ToolCall.objects.create(
            run_id=run_id,
            operation_id=uuid4(),
            sequence=1,
            tool="get_records",
            arguments_json='{"categories":["weather"]}',
        )

        def read():
            try:
                return read_run_progress(run_id, self.officer_id)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                AgentRun.objects.select_for_update().get(pk=run_id)
                result = pool.submit(read).result(timeout=3)
        self.assertEqual(result["calls"][0]["status"], "running")
        response = self.client.get(reverse("investigation-progress", args=[run_id]))
        self.assertContains(response, "Weather forecast")
        self.assertContains(response, "In progress")
        self.assertEqual(AgentRun.objects.get(pk=run_id).status, "active")
        self.assertEqual(ToolCall.objects.count(), 1)
        other = type(self.officer).objects.create_user(
            "other-walkthrough", first_name="Other Officer"
        )
        other.user_permissions.set(self.officer.user_permissions.all())
        self.client.force_login(other)
        foreign = self.client.get(reverse("investigation-progress", args=[run_id]))
        self.assertNotContains(foreign, "Weather forecast")
        self.assertNotContains(foreign, "Open recorded investigation")

    def test_stale_draft_points_to_current_application_and_has_no_review_form(self):
        saved = self.save()
        details = fixtures.ApplicationTests.investigate(self, saved)
        latest = self.save(previous=saved.application_id)
        response = self.client.get(reverse("saved-draft", args=[details["draft_id"]]))
        self.assertContains(response, f"Open current application v{latest.version}")
        self.assertContains(response, reverse("application-intake", args=[latest.application_id]))
        self.assertNotContains(response, 'name="review_token"')
