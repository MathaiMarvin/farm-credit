# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import json
from unittest.mock import patch

import test_applications as fixtures
from asgiref.sync import sync_to_async
from django.db import connections
from django.test import SimpleTestCase, TransactionTestCase
from django.urls import reverse
from test_model_investigation import LocalTools, ScriptedProvider

from farmcredit.adapters.agent_conversation import previous_response
from farmcredit.adapters.agent_runs import run_details, start_run
from farmcredit.adapters.model_investigation import investigate_model
from farmcredit.adapters.persistence.models import AgentRun
from farmcredit.application.investigation import DEFAULT_TASK, validate_task
from farmcredit.interfaces.web.walkthrough import activity_rows


class RequestTests(SimpleTestCase):
    def test_request_is_bounded_and_whitespace_is_normalised(self):
        self.assertEqual(validate_task("  Check obligations. \n"), "Check obligations.")
        for value in ("", " \n", "a" * 1001, None):
            with self.subTest(value=type(value)):
                with self.assertRaises(ValueError):
                    validate_task(value)

    def test_activity_shows_returned_findings_not_guessed_outcomes(self):
        call = {"tool": "get_records", "status": "running", "arguments": {}}
        self.assertEqual(activity_rows([call])[0]["findings"], [])
        call.update(
            status="succeeded",
            result={
                "groups": [
                    {
                        "category": "repayment_history",
                        "status": "unavailable",
                        "explanation": "Repayment history was not supplied.",
                    }
                ]
            },
        )
        self.assertEqual(activity_rows([call])[0]["needs_review"], 1)
        finding = activity_rows([call])[0]["findings"][0]
        self.assertEqual(finding["status"], "unavailable")
        self.assertEqual(finding["explanation"], "Repayment history was not supplied.")


class AgentWorkspaceTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save

    def launch(self, application_id, officer_id, run_id=None, task=DEFAULT_TASK):
        previous = previous_response(application_id, officer_id)
        run_id = start_run(
            application_id=application_id,
            officer_id=officer_id,
            run_id=run_id,
            model="scripted-test",
            request_context={"task": task, "previous_response": previous},
        )
        asyncio.run(
            investigate_model(
                run_id=run_id,
                officer_id=officer_id,
                provider=ScriptedProvider(),
                client=LocalTools(run_id, officer_id),
                tools=[],
                task=task,
                previous=previous,
            )
        )
        asyncio.run(sync_to_async(connections.close_all, thread_sensitive=True)())
        return run_id

    def test_task_reaches_model_and_saved_response_returns_to_workspace(self):
        saved = self.save(fixtures.intake_data(complete=True))
        url = reverse("application-intake", args=[saved.application_id])
        page = self.client.get(url)
        task = "Investigate the household obligations and tell me what needs attention."
        post = {
            "mode": "model",
            "conversation": "true",
            "task": task,
            "investigation_token": page.context["investigation_token"],
        }
        with patch(
            "farmcredit.interfaces.web.application_views.investigate_application_with_model",
            side_effect=self.launch,
        ) as launcher:
            response = self.client.post(
                reverse("application-investigate", args=[saved.application_id]),
                post,
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(
                response["HX-Redirect"],
                url + f"?investigation={page.context['run_id']}#agent-thread",
            )
            self.client.post(reverse("application-investigate", args=[saved.application_id]), post)
            self.assertEqual(launcher.call_count, 1)
        run = AgentRun.objects.get()
        details = run_details(run_id=str(run.pk), officer_id=self.officer_id)
        self.assertEqual(details["status"], "completed")
        request = next(e["payload"] for e in details["events"] if e["kind"] == "model_request")
        self.assertEqual(json.loads(request["messages"][1]["content"])["officer_request"], task)
        page = self.client.get(url)
        self.assertContains(page, task)
        self.assertContains(page, "Review finding and sources")
        self.assertContains(page, "Give the agent a follow-up task")
        prior = previous_response(saved.application_id, self.officer_id)
        self.assertEqual(prior["task"], task)
        self.assertEqual(prior["draft_id"], str(run.draft_id))
        other = self.save(fixtures.intake_data(complete=True))
        self.assertIsNone(previous_response(other.application_id, self.officer_id))
        with self.assertRaises(PermissionError):
            previous_response(saved.application_id, "99999999")

    def test_invalid_task_never_starts_a_run(self):
        saved = self.save()
        with patch(
            "farmcredit.interfaces.web.application_views.investigate_application_with_model"
        ) as launch:
            for task in (" ", "a" * 1001):
                response = self.client.post(
                    reverse("application-investigate", args=[saved.application_id]),
                    {"mode": "model", "task": task},
                    HTTP_HX_REQUEST="true",
                )
                self.assertEqual(response.status_code, 409)
            launch.assert_not_called()
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_demo_preview_does_not_run_agent(self):
        response = self.client.get(reverse("application-new") + "?demo=DEMO-001")
        self.assertContains(response, "Open agent workspace")
        self.assertContains(response, "Inspect or adjust the application")
        self.assertEqual(AgentRun.objects.count(), 0)
