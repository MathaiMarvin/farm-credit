# SPDX-License-Identifier: AGPL-3.0-only
import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import test_applications as fixtures
from django.test import TransactionTestCase
from django.urls import reverse
from test_weather import forecast

from farmcredit.adapters.agent_runs import invoke_tool, start_run
from farmcredit.adapters.institution_demo import demo_application_data
from farmcredit.adapters.persistence.models import Draft


class WeatherFlowTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save
    investigate = fixtures.ApplicationTests.investigate

    def call(self, run, tool, arguments):
        return invoke_tool(
            run_id=run,
            officer_id=self.officer_id,
            operation_id=str(uuid4()),
            tool=tool,
            arguments=arguments,
        )

    def save_weather(self):
        return self.save({**demo_application_data("DEMO-001"), "weather_reference": "Nakuru"})

    def test_weather_snapshot_is_shared_by_tools_calculation_and_cited_draft(self):
        saved = self.save_weather()
        with patch(
            "farmcredit.adapters.weather_mcp.fetch_weather", new=AsyncMock(return_value=forecast())
        ) as fetch:
            run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        fetch.assert_awaited_once()
        with patch(
            "farmcredit.adapters.weather_mcp.fetch_weather",
            new=AsyncMock(side_effect=AssertionError("no refresh")),
        ):
            records = self.call(run, "get_records", {"categories": ["weather"]})
            self.assertEqual(records["status"], "succeeded", records)
            weather = records["result"]["weather"]
            calculation = self.call(
                run, "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
            )["result"]
            self.assertEqual(calculation["weather"], weather)
            self.assertEqual(
                calculation["comparison"]["baseline"]["cashflow"]["cash_after_repayment"], "40000"
            )
            result = self.call(
                run,
                "save_draft",
                {
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                    "calculation_id": calculation["calculation_id"],
                    "statements": [
                        {
                            "text": "The short forecast does not cover the planned crop season.",
                            "record_ids": [weather["sources"][0]["record_id"]],
                        }
                    ],
                    "questions": weather["review"]["questions"],
                },
            )
        self.assertEqual(result["status"], "succeeded", result)
        snapshot = json.loads(result["result"]["snapshot_json"])
        self.assertEqual(snapshot["weather"], weather)
        page = self.client.get(reverse("saved-draft", args=[result["result"]["draft_id"]]))
        self.assertContains(page, "Forecast does not cover the crop season")
        self.assertContains(page, "CC BY 4.0")
        self.assertContains(page, "model forecast")

    def test_weather_failure_still_saves_questions_and_preserves_harvest_assumptions(self):
        saved = self.save_weather()
        with patch(
            "farmcredit.adapters.weather_mcp.fetch_weather",
            new=AsyncMock(side_effect=TimeoutError()),
        ):
            details = self.investigate(saved)
        result = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
        self.assertEqual(result["weather"]["review"]["status"], "unavailable")
        self.assertTrue(any("weather evidence" in q for q in result["questions"]))
        self.assertEqual(
            result["calculation"]["comparison"]["baseline"]["cashflow"]["cash_after_repayment"],
            "40000",
        )
        page = self.client.get(reverse("saved-draft", args=[details["draft_id"]]))
        self.assertContains(page, "Usable weather evidence needed")

    def test_prefill_and_save_do_not_start_external_weather_server(self):
        with patch("farmcredit.adapters.weather_mcp.fetch_weather", new=AsyncMock()) as fetch:
            page = self.client.get(reverse("application-new"), {"demo": "DEMO-001"})
            self.assertEqual(page.context["form"].initial["weather_reference"], "Nakuru")
            saved = self.save_weather()
            self.client.get(reverse("application-intake", args=[saved.application_id]))
        fetch.assert_not_called()
