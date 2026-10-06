# SPDX-License-Identifier: AGPL-3.0-only
import json
from unittest.mock import patch
from uuid import uuid4

import test_applications as application_fixtures
from django.test import TransactionTestCase
from django.urls import reverse
from test_market import CSV

from farmcredit.adapters.agent_runs import invoke_tool, start_run
from farmcredit.adapters.institution_demo import demo_application_data
from farmcredit.adapters.persistence.models import AgentRun, Draft


class MarketFlowTests(TransactionTestCase):
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

    def saved_market_application(self):
        return self.save({**demo_application_data("DEMO-001"), "market_reference": "Nakuru"})

    def test_run_fetches_once_and_freezes_evidence_across_tools_and_cited_draft(self):
        saved = self.saved_market_application()
        with patch("farmcredit.adapters.market_hdx.download_prices", return_value=CSV) as download:
            run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        download.assert_called_once()
        with patch(
            "farmcredit.adapters.market_hdx.download_prices",
            side_effect=AssertionError("must not refetch"),
        ):
            records = self.call(run, "get_records", {"categories": ["market_prices"]})
            self.assertEqual(records["status"], "succeeded", records)
            market = records["result"]["market"]
            self.assertEqual(market["review"]["status"], "stale")
            calculation = self.call(
                run, "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
            )["result"]
            self.assertEqual(calculation["market"], market)
            self.assertEqual(
                calculation["comparison"]["baseline"]["cashflow"]["cash_after_repayment"], "40000"
            )
            draft = self.call(
                run,
                "save_draft",
                {
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                    "calculation_id": calculation["calculation_id"],
                    "statements": [
                        {
                            "text": "The available Nakuru quotation is historical wholesale evidence.",
                            "record_ids": [market["sources"][0]["record_id"]],
                        }
                    ],
                    "questions": market["review"]["questions"],
                },
            )
        self.assertEqual(draft["status"], "succeeded", draft)
        snapshot = json.loads(draft["result"]["snapshot_json"])
        self.assertEqual(snapshot["market"], market)
        page = self.client.get(reverse("saved-draft", args=[draft["result"]["draft_id"]]))
        self.assertContains(page, "Historical price — current quote needed")
        self.assertContains(page, "CC BY 3.0 IGO")
        self.assertContains(page, "external evidence")

    def test_unavailable_and_incompatible_evidence_preserve_application_assumptions(self):
        for body in (TimeoutError(), CSV.replace(",KG,", ",bag,")):
            saved = self.saved_market_application()
            with patch(
                "farmcredit.adapters.market_hdx.download_prices",
                side_effect=body if isinstance(body, Exception) else None,
                return_value=body,
            ):
                details = self.investigate(saved)
            snapshot = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
            self.assertEqual(
                snapshot["market"]["review"]["status"],
                "unavailable" if isinstance(body, Exception) else "incompatible",
            )
            self.assertEqual(
                snapshot["market"]["assumed_price_per_kg"],
                saved.snapshot["inputs"]["case"]["sale"]["price_per_kg"],
            )
            self.assertTrue(any("buyer quote" in q for q in snapshot["questions"]))
            self.assertEqual(
                snapshot["calculation"]["comparison"]["baseline"]["cashflow"][
                    "cash_after_repayment"
                ],
                "40000",
            )

    def test_get_pages_do_not_retrieve_and_selection_is_saved(self):
        with patch("farmcredit.adapters.market_hdx.download_prices") as download:
            page = self.client.get(reverse("application-new"), {"demo": "DEMO-001"})
            self.assertEqual(page.context["form"].initial["market_reference"], "Nakuru")
            saved = self.saved_market_application()
            self.client.get(reverse("application-intake", args=[saved.application_id]))
        download.assert_not_called()
        self.assertEqual(saved.snapshot["inputs"]["context"]["market_reference"], "Nakuru")
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_new_run_refreshes_evidence_without_changing_previous_draft(self):
        saved = self.saved_market_application()
        with patch("farmcredit.adapters.market_hdx.download_prices", return_value=CSV):
            first = self.investigate(saved)
        old = Draft.objects.get(pk=first["draft_id"]).snapshot_json
        with patch(
            "farmcredit.adapters.market_hdx.download_prices",
            return_value=CSV.replace("35.88", "40.00"),
        ):
            second = self.investigate(saved)
        newer = json.loads(Draft.objects.get(pk=second["draft_id"]).snapshot_json)
        self.assertEqual(newer["market"]["quote"]["price"], "40")
        self.assertEqual(Draft.objects.get(pk=first["draft_id"]).snapshot_json, old)
