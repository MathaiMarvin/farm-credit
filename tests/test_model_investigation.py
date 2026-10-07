# SPDX-License-Identifier: AGPL-3.0-only
"""Software contract tests with a scripted model; these are not agent evaluations."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import test_applications as fixtures
from asgiref.sync import sync_to_async
from django.db import IntegrityError, connection, connections
from django.test import TransactionTestCase
from django.urls import reverse

from farmcredit.adapters.agent_runs import invoke_tool, run_details, start_run
from farmcredit.adapters.model_investigation import investigate_model
from farmcredit.adapters.model_provider import MODEL, ProviderFailure
from farmcredit.adapters.persistence.models import (
    Draft,
    DraftReview,
    InvestigationEvent,
    RunEvidence,
)
from farmcredit.interfaces.mcp.investigation import investigate_application_with_model


class ScriptedProvider:
    model = MODEL

    def __init__(self, *, failure=None, invalid=False):
        self.failure = failure
        self.invalid = invalid
        self.count = 0

    async def complete(self, messages, tools, *, timeout):
        self.count += 1
        if self.failure and self.count <= self.failure:
            raise ProviderFailure("Scripted temporary outage.", retryable=True)
        outcomes = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        args = {}
        if self.invalid:
            name = "approve_credit"
        elif not outcomes:
            name = "get_case"
        elif outcomes[-1]["tool"] == "get_case":
            name, args = "get_records", {"categories": ["lender_policy", "repayment_history"]}
        elif outcomes[-1]["tool"] == "get_records" and not outcomes[0]["result"]["gaps"]:
            name, args = "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        else:
            name = "save_draft"
            calculation = next(
                (o["result"] for o in outcomes if o["tool"] == "assess_cashflow"), None
            )
            args = {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "calculation_id": calculation["calculation_id"] if calculation else None,
                "statements": [],
                "questions": ["Confirm the supplied synthetic records before review."],
            }
        return {
            "model": self.model,
            "id": f"script-{self.count}",
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"call-{self.count}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                ],
            },
            "usage": {"total_tokens": 100, "cost": "0.001"},
            "finish_reason": "tool_calls",
        }


class LocalTools:
    def __init__(self, run_id, officer_id):
        self.run_id, self.officer_id = run_id, officer_id

    async def call_tool(self, name, args):
        args = dict(args)
        result = await sync_to_async(invoke_tool, thread_sensitive=True)(
            run_id=self.run_id,
            officer_id=self.officer_id,
            operation_id=args.pop("operation_id"),
            tool=name,
            arguments=args,
        )
        return SimpleNamespace(structured_content=result, is_error=result["status"] != "succeeded")


class ModelInvestigationTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save

    def tearDown(self):
        asyncio.run(sync_to_async(connections.close_all, thread_sensitive=True)())
        super().tearDown()

    def run_model(self, *, complete=False, provider=None):
        saved = self.save(fixtures.intake_data(complete=complete))
        run_id = start_run(
            application_id=saved.application_id, officer_id=self.officer_id, model=MODEL
        )
        asyncio.run(
            investigate_model(
                run_id=run_id,
                officer_id=self.officer_id,
                provider=provider or ScriptedProvider(),
                client=LocalTools(run_id, self.officer_id),
                tools=[],
            )
        )
        return run_details(run_id=run_id, officer_id=self.officer_id)

    def test_scripted_missing_and_complete_paths_use_returned_evidence(self):
        for complete in (False, True):
            details = self.run_model(complete=complete)
            self.assertEqual(details["status"], "completed", details)
            tools = [c["tool"] for c in details["calls"]]
            self.assertEqual("assess_cashflow" in tools, complete)
            self.assertEqual(details["execution_kind"], "model")
            self.assertEqual(details["token_usage"], len(tools) * 100)
            self.assertEqual(details["cost"], "0.004" if complete else "0.003")
            self.assertFalse(DraftReview.objects.filter(draft_id=details["draft_id"]).exists())
            response = self.client.get(reverse("application-run", args=[details["run_id"]]))
            self.assertContains(response, "Investigation trace")
            self.assertNotContains(response, "Fixed internal tool sequence")

    def test_outage_retries_once_and_keeps_unknown_total_cost(self):
        provider = ScriptedProvider(failure=1)
        details = self.run_model(provider=provider)
        self.assertEqual(details["status"], "completed")
        self.assertEqual(provider.count, 4)
        self.assertIsNone(details["cost"])
        self.assertIsNone(details["token_usage"])
        self.assertEqual(sum(e["kind"] == "model_failure" for e in details["events"]), 1)

    def test_persistent_outage_stops_without_a_draft(self):
        provider = ScriptedProvider(failure=100)
        details = self.run_model(provider=provider)
        self.assertEqual(provider.count, 2)
        self.assertIn("Scripted temporary outage.", details["reason"])
        self.assertEqual(details["status"], "incomplete")
        self.assertFalse(Draft.objects.exists())

    def test_provider_wait_longer_than_run_budget_is_explained_without_retry(self):
        from unittest.mock import AsyncMock

        provider = ScriptedProvider()
        provider.complete = AsyncMock(
            side_effect=ProviderFailure(
                "Temporary provider budget exhausted.", retryable=True, retry_after=120
            )
        )
        details = self.run_model(provider=provider)
        self.assertEqual(provider.complete.await_count, 1)
        self.assertEqual(details["status"], "incomplete")
        self.assertIn("retry delay (120s)", details["reason"])
        self.assertIn("no automatic retry was sent", details["reason"])
        failure = next(e["payload"] for e in details["events"] if e["kind"] == "model_failure")
        self.assertEqual(failure["retry_after"], 120)
        self.assertFalse(failure["retry_scheduled"])
        self.assertFalse(Draft.objects.exists())

    def test_unsupported_action_is_recorded_and_never_executed(self):
        details = self.run_model(provider=ScriptedProvider(invalid=True))
        self.assertEqual(details["status"], "incomplete")
        self.assertEqual(details["calls"], [])
        self.assertTrue(any(e["kind"] == "tool_rejected" for e in details["events"]))

    def test_model_silence_is_not_success(self):
        class Silent(ScriptedProvider):
            async def complete(self, *args, **kwargs):
                return {"message": {"role": "assistant", "content": "All done"}, "usage": None}

        self.assertEqual(self.run_model(provider=Silent())["status"], "incomplete")

    def test_external_reads_are_lazy_frozen_and_not_requested_by_start(self):
        from django.utils import timezone

        from farmcredit.adapters.agent_runs import EXTERNAL_EVIDENCE
        from farmcredit.adapters.market_hdx import snapshot_market

        data = {**fixtures.intake_data(), "market_reference": "Nakuru"}
        saved = self.save(data)
        with patch("farmcredit.adapters.market_hdx.download_prices", side_effect=OSError):
            snapshot = snapshot_market(
                "Nakuru", as_of=timezone.localdate(), retrieved_at=timezone.now()
            )
        with patch("farmcredit.adapters.agent_runs.snapshot_market") as eager:
            run_id = start_run(
                application_id=saved.application_id, officer_id=self.officer_id, model=MODEL
            )
            eager.assert_not_called()
        from unittest.mock import Mock

        fetch = Mock(return_value=snapshot)
        original = EXTERNAL_EVIDENCE["market_prices"]
        with patch.dict(EXTERNAL_EVIDENCE, {"market_prices": (*original[:2], fetch)}):

            async def read():
                from uuid import uuid4

                client = LocalTools(run_id, self.officer_id)
                for _ in range(2):
                    result = await client.call_tool(
                        "get_records",
                        {
                            "operation_id": str(uuid4()),
                            "categories": ["market_prices"],
                        },
                    )
                    self.assertFalse(result.is_error)

            asyncio.run(read())
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(RunEvidence.objects.count(), 1)
        self.assertEqual(InvestigationEvent.objects.filter(kind="external_evidence").count(), 1)

    def test_trace_and_evidence_are_database_immutable(self):
        details = self.run_model()
        RunEvidence.objects.create(run_id=details["run_id"], category="weather", snapshot_json="{}")
        with connection.cursor() as cursor:
            for table in ("investigationevent", "runevidence"):
                with self.assertRaises(IntegrityError):
                    cursor.execute(f"DELETE FROM persistence_{table}")
            with self.assertRaises(IntegrityError):
                cursor.execute("UPDATE persistence_agentrun SET model='changed'")

    def test_missing_credentials_and_csrf_do_not_start_model_calls(self):
        saved = self.save()
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": ""}):
            response = self.client.post(
                reverse("application-investigate", args=[saved.application_id]), {"mode": "model"}
            )
        self.assertContains(response, "Set OPENROUTER_API_KEY", status_code=409)
        self.assertFalse(InvestigationEvent.objects.exists())

    def test_repeated_read_stops_at_model_budget(self):
        class Repeating(ScriptedProvider):
            async def complete(self, messages, tools, *, timeout):
                return await super().complete([], tools, timeout=timeout)

        provider = Repeating()
        details = self.run_model(provider=provider)
        self.assertEqual(details["status"], "incomplete")
        self.assertEqual(provider.count, 10)
        self.assertEqual(len(details["calls"]), 10)
        self.assertFalse(Draft.objects.exists())

    def test_real_own_mcp_transport_with_scripted_model(self):
        saved = self.save()
        with patch(
            "farmcredit.interfaces.mcp.investigation.OpenRouter.configured",
            return_value=ScriptedProvider(),
        ):
            run_id = investigate_application_with_model(
                application_id=saved.application_id, officer_id=self.officer_id
            )
        details = run_details(run_id=run_id, officer_id=self.officer_id)
        self.assertEqual(details["status"], "completed", details)
        self.assertTrue(any(e["kind"] == "mcp_discovery" for e in details["events"]))
