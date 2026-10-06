# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import json
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

import test_applications as application_fixtures
from django.test import TransactionTestCase
from django.urls import reverse

from farmcredit.adapters.agent_runs import invoke_tool, run_details, start_run
from farmcredit.adapters.application_store import get_application
from farmcredit.adapters.draft_reviews import draft_context
from farmcredit.adapters.institution_demo import DEMO_REVIEW_POLICY, demo_application_data
from farmcredit.adapters.persistence.models import AgentRun, ApplicationVersion, Draft
from farmcredit.application.institution_evidence import INSTITUTION_CATEGORIES
from farmcredit.interfaces.mcp.server import issue_run_token


class InstitutionFlowTests(TransactionTestCase):
    setUp = application_fixtures.ApplicationTests.setUp
    save = application_fixtures.ApplicationTests.save
    investigate = application_fixtures.ApplicationTests.investigate

    def call(self, run, tool, arguments):
        return invoke_tool(
            run_id=run,
            officer_id=self.officer_id,
            operation_id=str(uuid4()),
            tool=tool,
            arguments=arguments,
        )

    def test_three_files_change_findings_with_the_same_cashflow_assumptions(self):
        expectations = {
            "DEMO-001": ("advisory", "checks_satisfied", 4),
            "DEMO-002": ("evidence_request", "officer_review", 3),
            "DEMO-003": ("evidence_request", "evidence_required", 3),
        }
        for member, (kind, status, calls) in expectations.items():
            saved = self.save(demo_application_data(member))
            details = self.investigate(saved)
            draft = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
            self.assertEqual(draft["kind"], kind)
            self.assertEqual(draft["institution"]["review"]["status"], status)
            self.assertEqual(len(details["calls"]), calls)
            if member == "DEMO-001":
                baseline = draft["calculation"]["comparison"]["baseline"]["cashflow"]
                self.assertEqual(baseline["cash_after_repayment"], "40000")
                # KES 12,000 savings were not silently added to KES 40,000 cash.
                self.assertEqual(saved.snapshot["inputs"]["case"]["opening_cash"], "40000")
            else:
                self.assertIsNone(draft["calculation"]["comparison"])
                self.assertFalse(any(c["tool"] == "assess_cashflow" for c in details["calls"]))
            self.assertEqual(get_application(saved.application_id, self.officer_id), saved)
            self.assertNotIn("institution", saved.snapshot["inputs"])

    def test_record_retrieval_and_calculation_use_frozen_run_snapshot(self):
        saved = self.save(demo_application_data("DEMO-001"))
        run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        scope = json.loads(AgentRun.objects.get(pk=run).scope_json)
        stored = json.loads(scope["institution_snapshot_json"])
        with patch(
            "farmcredit.adapters.institution_demo.load_member_file",
            side_effect=AssertionError("must use frozen records"),
        ):
            first = self.call(run, "get_records", {"categories": list(INSTITUTION_CATEGORIES)})
            second = self.call(run, "get_records", {"categories": list(INSTITUTION_CATEGORIES)})
            calc = self.call(
                run, "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
            )
        self.assertEqual(first["status"], "succeeded", first)
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(first["result"]["institution_fingerprint"], stored["fingerprint"])
        self.assertEqual(calc["status"], "succeeded", calc)
        self.assertEqual(calc["result"]["institution"]["fingerprint"], stored["fingerprint"])
        self.assertEqual(get_application(saved.application_id, self.officer_id), saved)

    def test_missing_or_duplicate_obligation_blocks_calculation_without_rewriting_ledger(self):
        data = demo_application_data("DEMO-001")
        data["cash_records"] = "\n".join(
            line
            for line in data["cash_records"].splitlines()
            if not line.startswith("existing-debt,")
        )
        saved = self.save(data)
        details = self.investigate(saved)
        draft = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
        self.assertEqual(draft["kind"], "evidence_request")
        self.assertTrue(any("Reconcile existing-debt" in q for q in draft["questions"]))
        self.assertNotIn("existing-debt", saved.snapshot["inputs"]["intake"]["cash_records"])
        updated = self.save(demo_application_data("DEMO-001"), previous=saved.application_id)
        good = self.investigate(updated)
        result = json.loads(Draft.objects.get(pk=good["draft_id"]).snapshot_json)
        self.assertEqual(result["kind"], "advisory")
        self.assertEqual(
            result["calculation"]["comparison"]["baseline"]["cashflow"]["cash_after_repayment"],
            "40000",
        )

    def test_policy_change_invalidates_run_and_review_and_is_versioned_in_new_run(self):
        saved = self.save(demo_application_data("DEMO-001"))
        details = self.investigate(saved)
        active = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        review_page = self.client.get(reverse("saved-draft", args=[details["draft_id"]]))
        self.assertTrue(draft_context(details["draft_id"], self.officer_id)["current"])
        with patch(
            "farmcredit.adapters.institution_demo.DEMO_REVIEW_POLICY",
            replace(DEMO_REVIEW_POLICY, version="v2"),
        ):
            self.assertFalse(draft_context(details["draft_id"], self.officer_id)["current"])
            failed = self.call(active, "get_case", {})
            self.assertEqual(failed["status"], "failed")
            self.assertIn("policy changed", failed["error"])
            response = self.client.post(
                reverse("review-draft", args=[details["draft_id"]]),
                {
                    "review_token": review_page.context["review_token"],
                    "decision": "approved",
                    "note": "",
                },
            )
            self.assertEqual(response.status_code, 409)
            newer = self.investigate(saved)
            newer_draft = json.loads(Draft.objects.get(pk=newer["draft_id"]).snapshot_json)
            self.assertEqual(newer_draft["institution"]["policy"]["version"], "v2")
        self.assertEqual(
            json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)["institution"][
                "policy"
            ]["version"],
            "v1",
        )

    def test_institution_citations_are_bound_and_render_as_sources(self):
        saved = self.save(demo_application_data("DEMO-001"))
        run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        calc = self.call(
            run, "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        )
        draft = self.call(
            run,
            "save_draft",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "calculation_id": calc["result"]["calculation_id"],
                "statements": [
                    {
                        "text": "The recorded savings include a restricted balance.",
                        "record_ids": ["DEMO-001:savings"],
                    }
                ],
                "questions": [],
            },
        )
        self.assertEqual(draft["status"], "succeeded", draft)
        page = self.client.get(reverse("saved-draft", args=[draft["result"]["draft_id"]]))
        self.assertContains(page, "DEMO-001:savings")
        self.assertContains(page, "Neither amount is added to available cash")
        other_run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        other_calc = self.call(
            other_run, "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        )
        invalid = self.call(
            other_run,
            "save_draft",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "calculation_id": other_calc["result"]["calculation_id"],
                "statements": [{"text": "Wrong member record", "record_ids": ["DEMO-002:savings"]}],
                "questions": [],
            },
        )
        self.assertEqual(invalid["status"], "failed")
        self.assertIn("citation", invalid["error"])

    def test_changing_linked_file_requires_new_application_version(self):
        saved = self.save(demo_application_data("DEMO-001"))
        run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        updated = self.save(demo_application_data("DEMO-002"), previous=saved.application_id)
        self.assertEqual(updated.version, 2)
        self.assertEqual(
            self.call(run, "get_records", {"categories": ["repayment_history"]})["status"], "failed"
        )
        self.assertEqual(
            get_application(saved.application_id, self.officer_id).snapshot["inputs"][
                "institution_record_set"
            ],
            "DEMO-001",
        )

    def test_demo_links_prefill_reviewable_forms_without_writing_on_get(self):
        listing = self.client.get(reverse("applications"))
        for member in ("DEMO-001", "DEMO-002", "DEMO-003"):
            self.assertContains(listing, f"?demo={member}")
            form = self.client.get(reverse("application-new"), {"demo": member})
            self.assertEqual(form.status_code, 200)
            self.assertEqual(form.context["form"].initial["institution_record_set"], member)
        self.assertEqual(ApplicationVersion.objects.count(), 0)
        self.assertEqual(
            self.client.get(reverse("application-new"), {"demo": "OTHER"}).status_code, 400
        )

    def test_stdio_retrieves_only_the_bound_member_and_supplied_policy(self):
        from test_mcp import MCPTests

        saved = self.save(demo_application_data("DEMO-003"))
        self.run_id = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        self.token = issue_run_token(run_id=self.run_id, officer_id=self.officer_id)

        async def flow():
            async with MCPTests.mcp_client(self) as client:
                result = await client.call_tool(
                    "get_records",
                    {"operation_id": str(uuid4()), "categories": list(INSTITUTION_CATEGORIES)},
                )
                self.assertFalse(result.is_error, result)
                body = result.structured_content["result"]
                self.assertEqual(body["institution_review"]["status"], "evidence_required")
                history = next(
                    group for group in body["groups"] if group["category"] == "repayment_history"
                )
                self.assertEqual(history["status"], "unavailable")
                self.assertEqual(body["institution_policy"]["version"], "v1")
                rejected = await client.call_tool(
                    "get_records",
                    {
                        "operation_id": str(uuid4()),
                        "categories": ["repayment_history"],
                        "member_ref": "DEMO-001",
                    },
                )
                self.assertTrue(rejected.is_error)

        asyncio.run(flow())
        calls = run_details(run_id=self.run_id, officer_id=self.officer_id)["calls"]
        self.assertEqual([call["status"] for call in calls], ["succeeded", "failed"])
        self.assertIsNone(calls[-1]["result"])
