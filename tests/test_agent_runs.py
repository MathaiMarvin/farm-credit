# SPDX-License-Identifier: AGPL-3.0-only
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import test_save_draft as fixtures
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections
from django.test import TransactionTestCase

from farmcredit.adapters.agent_runs import invoke_tool, run_details, start_run
from farmcredit.adapters.case_reader import BoundCaseReader
from farmcredit.adapters.persistence.models import AgentRun, Draft, ToolCall


class AgentRunTests(TransactionTestCase):
    def setUp(self):
        fixtures.SaveDraftTests.setUp(self)
        self.run_id = start_run(
            officer_id=str(self.officer.pk), assessment_id=self.saved.assessment_id
        )

    def call(self, tool="get_case", arguments=None, operation_id=None, run_id=None):
        return invoke_tool(
            run_id=run_id or self.run_id,
            officer_id=str(self.officer.pk),
            operation_id=operation_id or str(uuid4()),
            tool=tool,
            arguments={} if arguments is None else arguments,
        )

    def details(self):
        return run_details(run_id=self.run_id, officer_id=str(self.officer.pk))

    def draft_arguments(self, calculation):
        return {
            "price_reduction": "20",
            "harvest_reduction": "20",
            "calculation_id": calculation,
            "statements": [
                {"text": item.text, "record_ids": list(item.record_ids)}
                for item in self.request.statements
            ],
            "questions": [],
        }

    def test_real_tool_flow_records_arguments_results_and_linked_draft(self):
        first = self.call()
        self.assertEqual(first["result"]["assessment_id"], self.saved.assessment_id)
        self.call("get_records", {"categories": ["harvest", "repayment_history"]})
        calculation = self.call(
            "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        )
        op = str(uuid4())
        arguments = self.draft_arguments(calculation["result"]["calculation_id"])
        saved = self.call("save_draft", arguments, op)
        self.assertEqual(saved["status"], "succeeded")
        self.assertEqual(self.call("save_draft", arguments, op), saved)
        details = self.details()
        self.assertEqual(details["status"], "completed")
        self.assertEqual(details["draft_id"], saved["result"]["draft_id"])
        self.assertEqual([c["sequence"] for c in details["calls"]], [1, 2, 3, 4])
        self.assertTrue(all(c["finished_at"] for c in details["calls"]))
        self.assertEqual(details["execution_kind"], "internal_tools")
        self.assertIsNone(details["token_usage"])
        self.assertIsNone(details["model"])
        self.assertEqual(Draft.objects.count(), 1)
        with self.assertRaises(ValueError):
            self.call()

    def test_read_retry_is_safe_and_changed_payload_rejected(self):
        op = str(uuid4())
        first = self.call(operation_id=op)
        self.assertEqual(first, self.call(operation_id=op))
        self.assertEqual(ToolCall.objects.count(), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.call(arguments={"case_id": "OTHER"}, operation_id=op)

    def test_wrong_officer_and_revoked_permission_cannot_read_or_execute(self):
        other = get_user_model().objects.create_user("other-runner", first_name="Other")
        other.user_permissions.set(self.officer.user_permissions.all())
        with self.assertRaises(LookupError):
            run_details(run_id=self.run_id, officer_id=str(other.pk))
        self.officer.user_permissions.clear()
        with self.assertRaises(PermissionError):
            self.call()
        with self.assertRaises(PermissionError):
            self.details()

    def test_changed_case_records_failure_without_using_new_inputs(self):
        self.store.record_current_inputs("FC-001", "changed")
        result = self.call()
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["result"])
        self.assertEqual(self.details()["status"], "incomplete")
        with self.assertRaises(ValueError):
            start_run(officer_id=str(self.officer.pk), assessment_id=self.saved.assessment_id)

    def test_no_approval_tool_and_no_replacement_financial_inputs(self):
        with self.assertRaises(ValueError):
            self.call("approve")
        result = self.call(
            "assess_cashflow",
            {"price_reduction": "20", "harvest_reduction": "20", "opening_cash": "99999"},
        )
        self.assertEqual(result["status"], "failed")
        self.assertEqual(self.details()["status"], "incomplete")

    def test_foreign_or_unexecuted_calculation_cannot_be_saved(self):
        result = self.call("save_draft", self.draft_arguments(self.request.calculation_id))
        self.assertEqual(result["status"], "failed")
        self.assertFalse(Draft.objects.exists())
        self.assertIn("from this run", result["error"])

    def test_call_limit_and_elapsed_deadline_are_enforced(self):
        for _ in range(12):
            self.assertEqual(self.call()["status"], "succeeded")
        with self.assertRaisesRegex(ValueError, "limit"):
            self.call()
        self.assertEqual(ToolCall.objects.count(), 12)
        self.assertEqual(self.details()["status"], "incomplete")
        run_id = start_run(officer_id=str(self.officer.pk), assessment_id=self.saved.assessment_id)
        started = AgentRun.objects.get(pk=run_id).started_at
        with patch(
            "farmcredit.adapters.agent_runs.timezone.now",
            return_value=started + timedelta(seconds=121),
        ):
            with self.assertRaisesRegex(ValueError, "deadline"):
                self.call(run_id=run_id)
        self.assertEqual(AgentRun.objects.get(pk=run_id).status, "incomplete")

    def test_unexpected_failure_is_recorded_without_exception_details(self):
        with patch.object(
            BoundCaseReader, "get_records", side_effect=RuntimeError("private provider detail")
        ):
            result = self.call("get_records", {"categories": ["harvest"]})
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("private provider detail", result["error"])
        self.assertEqual(self.details()["status"], "incomplete")

    def test_interrupted_call_remains_visible_and_cannot_be_reexecuted(self):
        op = str(uuid4())
        with patch("farmcredit.adapters.agent_runs._execute", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.call(operation_id=op)
        self.assertEqual(self.call(operation_id=op)["status"], "running")
        with self.assertRaisesRegex(ValueError, "in progress"):
            self.call()
        started = AgentRun.objects.get(pk=self.run_id).started_at
        with patch(
            "farmcredit.adapters.agent_runs.timezone.now",
            return_value=started + timedelta(seconds=121),
        ):
            details = self.details()
        self.assertEqual(details["status"], "incomplete")
        self.assertEqual(details["calls"][0]["status"], "running")
        self.assertIsNone(details["calls"][0]["result"])

    def test_late_result_is_not_confirmed(self):
        started = AgentRun.objects.get(pk=self.run_id).started_at
        original = BoundCaseReader.get_records
        with patch(
            "farmcredit.adapters.agent_runs.timezone.now",
            return_value=started + timedelta(seconds=1),
        ) as clock:

            def late(reader, categories):
                result = original(reader, categories)
                clock.return_value = started + timedelta(seconds=121)
                return result

            with patch.object(BoundCaseReader, "get_records", late):
                result = self.call("get_records", {"categories": ["harvest"]})
        self.assertEqual(result["status"], "failed")
        self.assertIsNone(result["result"])

    def test_failed_save_rolls_back_draft_and_preserves_failed_event(self):
        calculation = self.call(
            "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        )
        arguments = self.draft_arguments(calculation["result"]["calculation_id"])
        op = str(uuid4())
        with patch(
            "farmcredit.adapters.agent_runs.save_draft", side_effect=RuntimeError("unavailable")
        ):
            first = self.call("save_draft", arguments, op)
        self.assertEqual(first["status"], "failed")
        self.assertFalse(Draft.objects.exists())
        self.assertEqual(self.call("save_draft", arguments, op), first)
        self.assertIsNone(self.details()["draft_id"])

    def test_missing_evidence_can_finish_with_an_evidence_request(self):
        from test_get_case import changed_snapshot

        incomplete = changed_snapshot(self.saved, lambda s: s["inputs"].update(evidence=[]))
        saved = self.store.save(incomplete.snapshot_json, str(uuid4()))
        self.store.record_current_inputs("FC-001", saved.snapshot["input_fingerprint"])
        self.run_id = start_run(officer_id=str(self.officer.pk), assessment_id=saved.assessment_id)
        calculation = self.call(
            "assess_cashflow", {"price_reduction": "20", "harvest_reduction": "20"}
        )
        self.assertIsNone(calculation["result"]["comparison"])
        arguments = {
            **self.draft_arguments(None),
            "statements": [],
            "questions": ["Provide the dated source records."],
        }
        result = self.call("save_draft", arguments)
        self.assertEqual(result["status"], "succeeded")
        self.assertIn('"kind":"evidence_request"', result["result"]["snapshot_json"])
        self.assertEqual(self.details()["status"], "completed")

    def test_final_tool_outcomes_and_bindings_cannot_be_rewritten(self):
        self.call()
        with connection.cursor() as cursor:
            for sql in (
                "UPDATE persistence_toolcall SET result_json = '{}'",
                "DELETE FROM persistence_toolcall",
                "UPDATE persistence_agentrun SET scope_json = '{}'",
                "DELETE FROM persistence_agentrun",
            ):
                with self.assertRaisesRegex(IntegrityError, "immutable"):
                    cursor.execute(sql)

    def test_concurrent_same_operation_executes_once(self):
        op = str(uuid4())

        def invoke(_):
            try:
                return self.call(operation_id=op)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(invoke, range(2)))
        self.assertEqual(ToolCall.objects.count(), 1)
        self.assertTrue(all(item["status"] in {"running", "succeeded"} for item in outcomes))
        self.assertEqual(self.call(operation_id=op)["status"], "succeeded")
