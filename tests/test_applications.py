# SPDX-License-Identifier: AGPL-3.0-only
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, OperationalError, connection, connections
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from farmcredit.adapters.agent_runs import invoke_tool, run_details, start_run
from farmcredit.adapters.application_store import get_application, save_application
from farmcredit.adapters.case_reader import bind_application_reader
from farmcredit.adapters.demo import load_demo_case, load_monthly_case
from farmcredit.adapters.draft_reviews import draft_context, review_draft
from farmcredit.adapters.intake_investigation import investigate_application
from farmcredit.adapters.persistence.models import ApplicationVersion, Assessment, Draft, ToolCall
from farmcredit.application.intake import INTAKE_FIELDS
from farmcredit.domain.draft_review import DraftReviewRequest
from farmcredit.domain.review import Officer
from farmcredit.interfaces.mcp.server import issue_run_token
from farmcredit.interfaces.web.forms import ApplicationForm


def intake_data(*, complete=False, monthly=False, farmer="Synthetic household A"):
    data = {
        "farmer": farmer,
        "crop": "maize",
        "repayment_mode": "monthly" if monthly else "seasonal",
        "source": "Synthetic officer intake worksheet",
        "recorded_on": timezone.localdate().isoformat(),
        "basis": "declared",
    }
    if complete:
        case = load_monthly_case() if monthly else load_demo_case()
        data.update(
            institution_record_set="DEMO-001",
            farm="Plot A",
            location="Synthetic Nakuru plot",
            season="2027 maize",
            area_hectares="1.00",
        )
        for field, _, _ in INTAKE_FIELDS:
            value = case
            for part in field.split("."):
                value = getattr(value, part)
            data[field.replace(".", "_")] = str(value) if value is not None else ""
        data["coverage_through"] = str(case.financing.repayment_on)
        data["schedule"] = "\n".join(
            f"{r.record_id}-supplied, {r.on}, {-r.amount}" for r in case.financing.as_repayments()
        )
        data["cash_records"] = "\n".join(
            f"{r.record_id}, {r.on}, {r.amount}" for r in case.other_movements
        )
        data.update(schedule_source="Synthetic supplied terms", schedule_version="v1")
    return data


class ApplicationTests(TransactionTestCase):
    def setUp(self):
        model = get_user_model()
        self.officer = model.objects.create_user("intake-officer", first_name="Synthetic Officer")
        permission, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(model),
            codename="review_assessment",
            defaults={"name": "Can review advisory"},
        )
        self.officer.user_permissions.add(permission)
        self.officer_id = str(self.officer.pk)
        self.client.force_login(self.officer)

    def save(self, data=None, previous=None, operation=None):
        form = ApplicationForm(data if data is not None else intake_data())
        self.assertTrue(form.is_valid(), form.errors)
        return save_application(
            officer_id=self.officer_id,
            inputs=form.inputs,
            operation_id=operation or str(uuid4()),
            previous_id=previous,
        )

    def investigate(self, saved):
        run = investigate_application(
            application_id=saved.application_id, officer_id=self.officer_id
        )
        details = run_details(run_id=run, officer_id=self.officer_id)
        self.assertEqual(details["status"], "completed", details)
        return details

    def test_unknown_yield_schedule_and_zero_survive_reopening(self):
        saved = self.save({**intake_data(), "opening_cash": "0"})
        reopened = get_application(saved.application_id, self.officer_id)
        self.assertEqual(reopened, saved)
        inputs = reopened.snapshot["inputs"]["case"]
        self.assertIsNone(inputs["sale"]["gross_kg"])
        self.assertEqual(inputs["opening_cash"], "0")
        self.assertEqual(inputs["financing"]["schedule"], [])
        self.assertIsNone(inputs["financing"]["repayment_on"])
        self.assertNotIn("result", saved.snapshot)
        self.assertFalse(Assessment.objects.exists())
        response = self.client.get(reverse("application-intake", args=[saved.application_id]))
        self.assertContains(response, "More evidence is needed")
        self.assertIsNone(response.context["form"].initial["sale_gross_kg"])

    def test_missing_provenance_can_be_saved_and_requests_sources(self):
        data = {**intake_data(complete=True), "source": "", "recorded_on": "", "basis": ""}
        saved = self.save(data)
        self.assertEqual(saved.snapshot["inputs"]["evidence"], [])
        details = self.investigate(saved)
        self.assertIn("missing source", Draft.objects.get(pk=details["draft_id"]).snapshot_json)

    def test_two_applications_and_their_evidence_stay_isolated(self):
        first = self.save({**intake_data(), "sale_gross_kg": "1000"})
        second = self.save({**intake_data(farmer="Synthetic household B"), "sale_gross_kg": "2500"})
        first_run, second_run = self.investigate(first), self.investigate(second)
        for saved, run, quantity in ((first, first_run, "1000"), (second, second_run, "2500")):
            case = run["calls"][0]["result"]
            self.assertEqual(case["application_id"], saved.application_id)
            self.assertEqual(
                next(f["value"] for f in case["facts"] if f["field"] == "sale.gross_kg"), quantity
            )
            self.assertEqual(
                Draft.objects.get(pk=run["draft_id"]).application_id.hex,
                saved.application_id.replace("-", ""),
            )
        self.assertNotEqual(first.case_id, second.case_id)
        self.assertEqual(get_application(first.application_id, self.officer_id), first)

    def test_incomplete_run_can_save_request_without_any_calculation_call(self):
        saved = self.save()
        details = self.investigate(saved)
        self.assertEqual(
            [call["tool"] for call in details["calls"]], ["get_case", "get_records", "save_draft"]
        )
        draft = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
        self.assertEqual(draft["kind"], "evidence_request")
        self.assertIsNone(draft["calculation"]["comparison"])
        self.assertTrue(draft["questions"])
        self.assertFalse(Assessment.objects.exists())
        self.assertEqual(get_application(saved.application_id, self.officer_id), saved)

    def test_seasonal_and_monthly_inputs_reach_authoritative_calculation(self):
        for monthly in (False, True):
            saved = self.save(intake_data(complete=True, monthly=monthly))
            details = self.investigate(saved)
            draft = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
            self.assertEqual(draft["kind"], "advisory", draft["calculation"])
            result = draft["calculation"]["comparison"]["baseline"]["cashflow"]
            self.assertEqual(len(result["repayments"]), 6 if monthly else 1)
            if not monthly:
                self.assertEqual(result["cash_after_repayment"], "40000")
            self.assertIsNone(details["assessment_id"])
            self.assertEqual(details["application_id"], saved.application_id)

    def test_invalid_totals_preserve_application_and_produce_request(self):
        data = intake_data(complete=True)
        data["financing_principal"] = "99999"
        saved = self.save(data)
        details = self.investigate(saved)
        draft = json.loads(Draft.objects.get(pk=details["draft_id"]).snapshot_json)
        self.assertEqual(draft["kind"], "evidence_request")
        self.assertIn("reconcile", draft["calculation"]["error"])

    def test_new_version_invalidates_active_run_review_and_stale_editor(self):
        saved = self.save()
        details = self.investigate(saved)
        context = draft_context(details["draft_id"], self.officer_id)
        self.assertTrue(context["current"])
        active = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        request = DraftReviewRequest(
            details["draft_id"],
            str(uuid4()),
            context["revision"],
            "approved",
            "",
            Officer(self.officer_id, "ignored", True),
        )
        updated = self.save(
            {**intake_data(), "sale_gross_kg": "2000"}, previous=saved.application_id
        )
        self.assertEqual(updated.version, 2)
        self.assertFalse(draft_context(details["draft_id"], self.officer_id)["current"])
        with self.assertRaises(ValueError):
            review_draft(request)
        with self.assertRaisesRegex(ValueError, "changed"):
            self.save(previous=saved.application_id)
        failed = invoke_tool(
            run_id=active,
            officer_id=self.officer_id,
            operation_id=str(uuid4()),
            tool="get_case",
            arguments={},
        )
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(get_application(saved.application_id, self.officer_id), saved)
        fresh = self.investigate(updated)
        review = review_draft(
            replace(
                request,
                draft_id=fresh["draft_id"],
                operation_id=str(uuid4()),
                expected_revision=draft_context(fresh["draft_id"], self.officer_id)["revision"],
            )
        )
        self.assertEqual(review.officer_name, "Synthetic Officer")

    def test_other_officer_cannot_read_edit_run_or_review_application(self):
        saved = self.save()
        details = self.investigate(saved)
        other = get_user_model().objects.create_user("other-intake", first_name="Other Officer")
        other.user_permissions.set(self.officer.user_permissions.all())
        other_id = str(other.pk)
        for action in (
            lambda: get_application(saved.application_id, other_id),
            lambda: bind_application_reader(
                application_id=saved.application_id, officer_id=other_id
            ),
            lambda: start_run(application_id=saved.application_id, officer_id=other_id),
            lambda: run_details(run_id=details["run_id"], officer_id=other_id),
            lambda: draft_context(details["draft_id"], other_id),
        ):
            with self.assertRaises(LookupError):
                action()
        self.client.force_login(other)
        for route, key in (
            ("application-intake", saved.application_id),
            ("application-run", details["run_id"]),
            ("saved-draft", details["draft_id"]),
        ):
            self.assertEqual(self.client.get(reverse(route, args=[key])).status_code, 404)
        self.assertNotContains(self.client.get(reverse("applications")), saved.case_id)

    def test_revocation_blocks_existing_application_and_run(self):
        saved = self.save()
        run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        self.officer.user_permissions.clear()
        with self.assertRaises(PermissionError):
            get_application(saved.application_id, self.officer_id)
        with self.assertRaises(PermissionError):
            run_details(run_id=run, officer_id=self.officer_id)

    def test_database_rejects_application_edits_deletes_and_run_rebinding(self):
        saved = self.save()
        start_run(application_id=saved.application_id, officer_id=self.officer_id)
        with connection.cursor() as cursor:
            for sql in (
                "UPDATE persistence_applicationversion SET snapshot_json = '{}'",
                "DELETE FROM persistence_applicationversion",
                "UPDATE persistence_agentrun SET application_id = NULL",
            ):
                with self.assertRaises(IntegrityError):
                    cursor.execute(sql)

    def test_save_retry_concurrency_and_competing_edits(self):
        operation = str(uuid4())

        def save(_):
            try:
                return self.save(operation=operation)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(ApplicationVersion.objects.count(), 1)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            self.save({**intake_data(), "sale_gross_kg": "1000"}, operation=operation)

    def test_competing_edits_create_one_successor(self):
        saved = self.save()

        def edit(quantity):
            try:
                try:
                    return self.save(
                        {**intake_data(), "sale_gross_kg": quantity}, previous=saved.application_id
                    ).version
                except ValueError:
                    return "stale"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(edit, ["1000", "2000"]))
        self.assertCountEqual(outcomes, [2, "stale"])
        self.assertEqual(ApplicationVersion.objects.count(), 2)

    def test_old_assessment_stays_readable_and_current(self):
        from test_get_case import saved_fixture

        from farmcredit.adapters.assessment_store import AssessmentStore

        store = AssessmentStore()
        assessment = store.save(saved_fixture().snapshot_json, str(uuid4()))
        store.record_current_inputs("FC-001", assessment.snapshot["input_fingerprint"])
        saved = self.save()
        self.investigate(saved)
        self.save({**intake_data(), "sale_gross_kg": "1000"}, previous=saved.application_id)
        self.assertEqual(store.get(assessment.assessment_id), assessment)
        self.assertTrue(store.review_context(assessment.assessment_id)["current"])
        self.assertEqual(
            self.client.get(
                reverse("saved-assessment", args=[assessment.assessment_id])
            ).status_code,
            200,
        )

    def test_web_storage_failure_and_failed_run_are_visible(self):
        page = self.client.get(reverse("application-new"))
        with patch(
            "farmcredit.interfaces.web.application_views.save_application",
            side_effect=OperationalError("secret database detail"),
        ):
            failed = self.client.post(
                reverse("application-new"),
                {**intake_data(), "save_token": page.context["save_token"]},
            )
        self.assertEqual(failed.status_code, 503)
        self.assertNotContains(failed, "secret database detail", status_code=503)
        saved = self.save()
        run = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        self.save({**intake_data(), "sale_gross_kg": "1000"}, previous=saved.application_id)
        invoke_tool(
            run_id=run,
            officer_id=self.officer_id,
            operation_id=str(uuid4()),
            tool="get_case",
            arguments={},
        )
        response = self.client.get(reverse("application-run", args=[run]))
        self.assertContains(response, "Evidence check · incomplete")
        self.assertContains(response, "The case changed")

    def test_web_save_reopen_investigate_review_and_edit_flow(self):
        page = self.client.get(reverse("application-new"))
        response = self.client.post(
            reverse("application-new"), {**intake_data(), "save_token": page.context["save_token"]}
        )
        self.assertEqual(response.status_code, 302)
        page = self.client.get(response.url)
        saved = page.context["saved"]
        run = self.client.post(
            reverse("application-investigate", args=[saved.application_id]), follow=True
        )
        self.assertContains(run, "Evidence check · completed")
        draft_id = run.context["run"]["draft_id"]
        draft = self.client.get(reverse("saved-draft", args=[draft_id]))
        self.assertContains(draft, "Approve evidence request")
        review = self.client.post(
            reverse("review-draft", args=[draft_id]),
            {
                "review_token": draft.context["review_token"],
                "decision": "approved",
                "note": "Request the missing source records.",
            },
            follow=True,
        )
        self.assertContains(review, "Evidence request approved")
        edited = self.client.post(
            response.url,
            {**intake_data(), "sale_gross_kg": "1000", "save_token": page.context["save_token"]},
        )
        self.assertEqual(edited.status_code, 302)
        self.assertContains(
            self.client.get(reverse("saved-draft", args=[draft_id])), "decision is historical"
        )

    def test_form_errors_tampering_csrf_and_unsupported_crop(self):
        for changes in (
            {"schedule": "p, 2027-09-01, -100"},
            {"schedule": "p, 2027-09-01, NaN"},
            {"sale_gross_kg": "-1"},
            {"recorded_on": "2999-01-01"},
            {"schedule": "p, 2027-09-01, 100\np, 2027-09-01, 100"},
        ):
            form = ApplicationForm({**intake_data(), **changes})
            self.assertFalse(form.is_valid())
        self.assertEqual(
            self.client.post(reverse("application-new"), intake_data()).status_code, 400
        )
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.officer)
        self.assertEqual(csrf.post(reverse("application-new"), intake_data()).status_code, 403)
        saved = self.save({**intake_data(complete=True), "crop": "other"})
        details = self.investigate(saved)
        self.assertIn(
            "only maize is supported", Draft.objects.get(pk=details["draft_id"]).snapshot_json
        )

    def test_application_bound_stdio_can_request_evidence_without_calculation(self):
        from test_mcp import MCPTests

        saved = self.save()
        self.run_id = start_run(application_id=saved.application_id, officer_id=self.officer_id)
        self.token = issue_run_token(run_id=self.run_id, officer_id=self.officer_id)

        async def flow():
            async with MCPTests.mcp_client(self) as client:
                case = await client.call_tool("get_case", {"operation_id": str(uuid4())})
                self.assertFalse(case.is_error)
                self.assertEqual(
                    case.structured_content["result"]["application_id"], saved.application_id
                )
                draft = await client.call_tool(
                    "save_draft",
                    {
                        "operation_id": str(uuid4()),
                        "price_reduction": "20",
                        "harvest_reduction": "20",
                        "calculation_id": None,
                        "statements": [],
                        "questions": ["Provide the supplied schedule and harvest evidence."],
                    },
                )
                self.assertFalse(draft.is_error, draft)

        asyncio.run(flow())
        self.assertEqual(ToolCall.objects.count(), 2)
