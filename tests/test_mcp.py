# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import sys
from unittest.mock import patch
from uuid import uuid4

import test_save_draft as fixtures
from django.conf import settings
from django.db import connection
from django.test import TransactionTestCase
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from farmcredit.adapters.agent_runs import run_details, start_run
from farmcredit.adapters.persistence.models import Draft, ToolCall
from farmcredit.interfaces.mcp.server import _binding, issue_run_token


class MCPTests(TransactionTestCase):
    def setUp(self):
        fixtures.SaveDraftTests.setUp(self)
        self.run_id = start_run(
            officer_id=str(self.officer.pk), assessment_id=self.saved.assessment_id
        )
        self.token = issue_run_token(run_id=self.run_id, officer_id=str(self.officer.pk))

    def mcp_client(self):
        database = connection.settings_dict
        env = {"FARMCREDIT_SECRET_KEY": settings.SECRET_KEY, "FARMCREDIT_MCP_TOKEN": self.token}
        for variable, key in (
            ("PGDATABASE", "NAME"),
            ("PGUSER", "USER"),
            ("PGPASSWORD", "PASSWORD"),
            ("PGHOST", "HOST"),
            ("PGPORT", "PORT"),
        ):
            env[variable] = str(database[key])
        return Client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "farmcredit.interfaces.mcp.run"], env=env
            )
        )

    def test_stdio_discovery_calculation_draft_and_retry(self):
        async def flow():
            async with self.mcp_client() as client:
                listing = await client.list_tools()
                self.assertEqual(
                    {t.name for t in listing.tools},
                    {"get_case", "get_records", "assess_cashflow", "save_draft"},
                )
                for tool in listing.tools:
                    self.assertFalse(tool.input_schema["additionalProperties"])
                    self.assertNotIn("officer_id", tool.input_schema["properties"])

                async def call(name, **args):
                    result = await client.call_tool(name, {"operation_id": str(uuid4()), **args})
                    self.assertFalse(result.is_error, result)
                    return result.structured_content

                case = await call("get_case")
                self.assertEqual(case["result"]["assessment_id"], self.saved.assessment_id)
                await call("get_records", categories=["harvest", "repayment_history"])
                calculation = await call(
                    "assess_cashflow", price_reduction="20", harvest_reduction="20"
                )
                args = {
                    "operation_id": str(uuid4()),
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                    "calculation_id": calculation["result"]["calculation_id"],
                    "statements": [
                        {"text": s.text, "record_ids": list(s.record_ids)}
                        for s in self.request.statements
                    ],
                    "questions": [],
                }
                draft = await client.call_tool("save_draft", args)
                self.assertFalse(draft.is_error, draft)
                retry = await client.call_tool("save_draft", args)
                self.assertEqual(draft.structured_content, retry.structured_content)

        asyncio.run(flow())
        self.assertEqual(ToolCall.objects.count(), 4)
        self.assertEqual(Draft.objects.count(), 1)
        self.assertEqual(
            run_details(run_id=self.run_id, officer_id=str(self.officer.pk))["status"], "completed"
        )

    def test_stdio_rejects_identity_override_and_unknown_tools(self):
        async def flow():
            async with self.mcp_client() as client:
                for name, extras in (("get_case", {"officer_id": "someone"}), ("approve", {})):
                    result = await client.call_tool(name, {"operation_id": str(uuid4()), **extras})
                    self.assertTrue(result.is_error)

        asyncio.run(flow())
        self.assertFalse(Draft.objects.exists())
        self.assertFalse(ToolCall.objects.filter(status="succeeded").exists())

    def test_revoked_officer_cannot_use_issued_credential(self):
        self.officer.user_permissions.clear()

        async def flow():
            async with self.mcp_client() as client:
                result = await client.call_tool("get_case", {"operation_id": str(uuid4())})
                self.assertTrue(result.is_error)

        asyncio.run(flow())
        self.assertFalse(ToolCall.objects.exists())

    def test_credentials_expire_and_cannot_be_tampered_or_minted_for_other_officer(self):
        with self.assertRaises(PermissionError):
            _binding(self.token + "tampered")
        with patch("django.core.signing.time.time", return_value=9999999999):
            with self.assertRaises(PermissionError):
                _binding(self.token)
        with self.assertRaises(PermissionError):
            issue_run_token(run_id=self.run_id, officer_id="999999")
