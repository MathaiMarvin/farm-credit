# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise authenticated web flows in the isolated PostgreSQL test database."""

import os
import secrets
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farmcredit.interfaces.web.settings")

import django

django.setup()

from django.contrib.staticfiles import finders
from django.test import Client, TransactionTestCase, override_settings

from farmcredit.adapters.demo import load_demo_evidence


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthenticatedWebTests(TransactionTestCase):
    databases = {"default"}

    def setUp(self):
        from django.contrib.auth import get_user_model

        model = get_user_model()
        model.objects.all().delete()
        self.password = secrets.token_urlsafe(24)
        self.user = model.objects.create_user("workspace-reader", password=self.password)
        self.client.force_login(self.user)


@override_settings(ALLOWED_HOSTS=["testserver"], ROOT_URLCONF="legacy_urls")
class WorkspaceTests(AuthenticatedWebTests):
    def test_packaged_assets_are_available(self):
        for asset in ("workspace.css", "workspace.js", "vendor/htmx.min.js", "vendor/htmx.LICENSE"):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(f"farmcredit/{asset}"))

    def test_initial_page_is_a_synthetic_case_not_an_assessment(self):
        response = self.client.get("/")
        self.assertContains(response, "Demo household FC-001")
        self.assertContains(response, "This calculation is not a credit decision")
        self.assertNotContains(response, "No shortfall in this scenario")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Inspect input sources (34)")
        self.assertContains(response, "Supplied cooperative planning worksheet")

    def test_scenario_edits_are_assumptions_not_cooperative_observations(self):
        response = self.client.post(
            "/",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-10-15",
                "price_per_kg": "30",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "scenario:sale.price_per_kg")
        self.assertContains(response, "scenario:sale.received_on")
        self.assertContains(response, "Unsaved scenario edit; replaces demo:sale.price_per_kg")
        self.assertContains(response, "40 KES/kg")
        self.assertContains(response, "assumed")

    def test_missing_evidence_shows_a_gap_instead_of_a_result(self):
        with patch("farmcredit.interfaces.web.views.load_demo_evidence", return_value=()):
            response = self.client.post(
                "/",
                {
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                    "received_on": "2027-09-10",
                    "price_per_kg": "40",
                },
            )
        self.assertContains(response, "Further evidence required")
        self.assertContains(response, "missing source")
        self.assertNotContains(response, 'id="result-summary"')

    def test_source_text_is_escaped(self):
        records = load_demo_evidence()
        malicious = replace(records[0], source="<script>alert('source')</script>")
        with patch(
            "farmcredit.interfaces.web.views.load_demo_evidence",
            return_value=(malicious, *records[1:]),
        ):
            response = self.client.get("/")
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")

    def test_form_submission_calculates_case_without_javascript(self):
        response = self.client.post(
            "/",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-09-10",
                "price_per_kg": "40",
            },
        )
        self.assertContains(response, "No shortfall in this scenario")
        self.assertContains(response, "KSh 40,000.00")
        self.assertContains(response, "<!doctype html>")

    def test_htmx_submission_returns_partial_with_late_receipt_shortfall(self):
        response = self.client.post(
            "/",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-10-15",
                "price_per_kg": "40",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Repayment timing shortfall")
        self.assertContains(response, "KSh 20,000.00")
        self.assertContains(response, "Expected after the deadline")
        self.assertNotContains(response, "<!doctype html>")

    def test_changed_price_reaches_calculator(self):
        response = self.client.post(
            "/",
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-09-10",
                "price_per_kg": "10",
            },
        )
        self.assertContains(response, "KSh 5,000.00")
        self.assertContains(response, "Repayment timing shortfall")

    def test_invalid_inputs_return_errors_without_result(self):
        for inputs in (
            {},
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "invalid",
                "price_per_kg": "40",
            },
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-09-10",
                "price_per_kg": "-1",
            },
            {
                "price_reduction": "20",
                "harvest_reduction": "20",
                "received_on": "2027-09-10",
                "price_per_kg": "NaN",
            },
        ):
            with self.subTest(inputs=inputs):
                response = self.client.post("/", inputs, HTTP_HX_REQUEST="true")
                self.assertContains(response, "We need a correction")
                self.assertNotContains(response, 'id="result-summary"')

    def test_unsupported_dates_show_domain_error(self):
        for receipt, expected in (("2027-08-01", "Pre-harvest"), ("2027-09-30", "ordering")):
            with self.subTest(receipt=receipt):
                response = self.client.post(
                    "/",
                    {
                        "price_reduction": "20",
                        "harvest_reduction": "20",
                        "received_on": receipt,
                        "price_per_kg": "40",
                    },
                )
                self.assertContains(response, expected)
                self.assertNotContains(response, 'id="result-summary"')

    def test_csrf_is_required_and_valid_token_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        self.assertEqual(
            client.post(
                "/",
                {"price_reduction": "20", "harvest_reduction": "20", "received_on": "2027-09-10"},
            ).status_code,
            403,
        )
        client.get("/")
        response = client.post(
            "/",
            {
                "received_on": "2027-09-10",
                "price_per_kg": "40",
                "price_reduction": "20",
                "harvest_reduction": "20",
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertContains(response, "No shortfall in this scenario")

    def test_unknown_routes_and_unsupported_methods_are_rejected(self):
        self.assertEqual(self.client.get("/unknown/").status_code, 404)
        self.assertEqual(self.client.delete("/").status_code, 405)

    def test_stress_results_and_impossible_harvest_are_explicit(self):
        response = self.client.post(
            "/",
            {
                "received_on": "2027-09-10",
                "price_per_kg": "40",
                "price_reduction": "50",
                "harvest_reduction": "50",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertContains(response, "Combined stress")
        self.assertContains(response, "KSh -10,000.00")
        self.assertContains(response, "Sensitivity tests, not predictions")
        response = self.client.post(
            "/",
            {
                "received_on": "2027-09-10",
                "price_per_kg": "40",
                "price_reduction": "20",
                "harvest_reduction": "100",
            },
        )
        self.assertContains(response, "not calculated")
        self.assertContains(response, "Retained harvest and losses exceed gross harvest.")
        self.assertContains(response, "KSh 40,000.00")

    def test_stress_percentages_are_required_and_validated(self):
        for value in ("", "-1", "101", "NaN"):
            response = self.client.post(
                "/",
                {
                    "received_on": "2027-09-10",
                    "price_per_kg": "40",
                    "price_reduction": value,
                    "harvest_reduction": "20",
                },
            )
            self.assertContains(response, "We need a correction")
            self.assertNotContains(response, 'id="result-summary"')

    def test_monthly_demo_displays_supplied_schedule(self):
        response = self.client.get("/", {"repayment_mode": "monthly"})
        self.assertContains(response, "Monthly instalments · supplied terms")
        self.assertContains(response, "demo-v1")
        self.assertContains(response, 'name="repayment_mode" value="monthly"')
        self.assertContains(response, "Inspect input sources (47)")
        self.assertNotContains(response, 'id="repayment-positions"')

    def test_monthly_form_shows_early_gap_and_positive_final_balance(self):
        for partial in (False, True):
            response = self.client.post(
                "/",
                {
                    "repayment_mode": "monthly",
                    "received_on": "2027-09-10",
                    "price_per_kg": "40",
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                },
                **({"HTTP_HX_REQUEST": "true"} if partial else {}),
            )
            self.assertContains(response, "Earlier cash shortfall")
            self.assertContains(response, "First cash gap: 15 Aug 2027")
            self.assertContains(response, "KSh -9,500.00")
            self.assertContains(response, "KSh 40,000.00")
            self.assertContains(response, 'id="repayment-positions"')
            self.assertNotContains(response, "Coverage:")
            self.assertContains(response, "Combined stress")

    def test_unknown_repayment_mode_is_rejected(self):
        self.assertEqual(self.client.get("/", {"repayment_mode": "unknown"}).status_code, 400)
        self.assertEqual(self.client.post("/", {"repayment_mode": "unknown"}).status_code, 400)

    def test_monthly_missing_source_blocks_results(self):
        with patch("farmcredit.interfaces.web.views.load_monthly_evidence", return_value=()):
            response = self.client.post(
                "/",
                {
                    "repayment_mode": "monthly",
                    "received_on": "2027-09-10",
                    "price_per_kg": "40",
                    "price_reduction": "20",
                    "harvest_reduction": "20",
                },
            )
        self.assertContains(response, "Further evidence required")
        self.assertNotContains(response, 'id="repayment-positions"')


@override_settings(ALLOWED_HOSTS=["testserver"], ROOT_URLCONF="legacy_urls")
class SavedAssessmentWebTests(AuthenticatedWebTests):
    def calculate(self, **changes):
        import html
        import re

        inputs = {
            "repayment_mode": "monthly",
            "received_on": "2027-09-10",
            "price_per_kg": "40",
            "price_reduction": "20",
            "harvest_reduction": "20",
            **changes,
        }
        response = self.client.post("/", inputs)
        match = re.search(r'name="calculation" value="([^"]+)"', response.content.decode())
        return response, html.unescape(match.group(1)) if match else None

    def test_guided_flow_shows_finding_before_save_and_review(self):
        calculation, token = self.calculate()
        body = calculation.content.decode()
        self.assertLess(body.index('id="result-summary"'), body.index('id="save-assessment-form"'))
        saved = self.client.post("/assessments/save/", {"calculation": token})
        detail = self.client.get(saved.url)
        body = detail.content.decode()
        self.assertLess(body.index('id="saved-result"'), body.index('id="review-heading"'))
        self.assertContains(detail, "advisory-review permission is required")
        self.assertContains(detail, "Sign out")
        self.assertNotContains(detail, "Complete saved snapshot")
        history = self.client.get("/assessments/")
        self.assertContains(history, "Cash gap from 2027-08-15")
        self.assertContains(history, "Awaiting officer review")
        self.assertContains(history, "Open assessment")

    def test_workspace_navigation_is_only_present_after_sign_in(self):
        for url in ("/", "/assessments/"):
            response = self.client.get(url)
            self.assertContains(response, 'aria-label="Workspace sections"')
            self.assertContains(response, "Sign out")
            self.assertContains(response, 'href="#main"')
        login = Client().get("/accounts/login/")
        self.assertContains(login, "Sign in to access farmer cases and assessments.")
        self.assertNotContains(login, 'aria-label="Workspace sections"')
        self.assertNotContains(login, "FC-001")
        self.assertContains(self.client.get("/assessments/"), "Start with the household case")

    def test_invalid_stress_setting_opens_optional_controls(self):
        response, token = self.calculate(price_reduction="101")
        self.assertIsNone(token)
        self.assertContains(
            response, "<details open><summary>Adjust stress tests (optional)</summary>"
        )
        self.assertContains(response, 'href="#id_price_reduction"')

    def test_save_reopen_history_and_retry(self):
        _, token = self.calculate()
        first = self.client.post("/assessments/save/", {"calculation": token})
        self.assertEqual(first.status_code, 302)
        second = self.client.post("/assessments/save/", {"calculation": token})
        self.assertEqual(first.url, second.url)
        with patch(
            "farmcredit.interfaces.web.views.compare_stress",
            side_effect=AssertionError("Saved pages must not recalculate"),
        ):
            detail = self.client.get(first.url)
        self.assertContains(detail, "Assessment v1")
        self.assertContains(detail, "Saved input sources (47)")
        self.assertContains(detail, "KSh 40,000.00")
        self.assertContains(detail, "2027-08-15")
        history = self.client.get("/assessments/")
        self.assertContains(history, "version 1")
        self.assertNotContains(history, "version 2")

    def test_reference_comparison_marks_changed_inputs_stale(self):
        _, token = self.calculate()
        saved = self.client.post("/assessments/save/", {"calculation": token})
        reference = saved.url.strip("/").split("/")[-1]
        initial = self.client.get("/", {"reference": reference})
        self.assertContains(initial, "Calculate to compare")
        unchanged, _ = self.calculate(reference=reference)
        self.assertContains(unchanged, "Current inputs, sources and policy match")
        changed, _ = self.calculate(reference=reference, price_per_kg="30")
        self.assertContains(changed, "Stale for these inputs")
        self.assertContains(self.client.get(saved.url), "KSh 40,000.00")

    def test_tampered_and_expired_tokens_are_rejected(self):
        from django.core import signing

        _, token = self.calculate()
        self.assertEqual(
            self.client.post("/assessments/save/", {"calculation": token + "tamper"}).status_code,
            400,
        )
        import time

        payload = signing.loads(token, salt="assessment-save")
        with patch("django.core.signing.time.time", return_value=time.time() - 1801):
            expired = signing.dumps(payload, salt="assessment-save")
        self.assertEqual(
            self.client.post("/assessments/save/", {"calculation": expired}).status_code, 400
        )
        self.assertContains(self.client.get("/assessments/"), "No assessments saved yet")

    def test_invalid_calculation_has_no_save_action(self):
        response, token = self.calculate(price_per_kg="-1")
        self.assertIsNone(token)
        self.assertNotContains(response, 'id="save-assessment-form"')

    def test_save_failure_preserves_retry_token(self):
        from django.db import OperationalError

        _, token = self.calculate()
        with patch(
            "farmcredit.interfaces.web.saved_views.AssessmentStore.save",
            side_effect=OperationalError("unavailable"),
        ):
            response = self.client.post("/assessments/save/", {"calculation": token})
        self.assertContains(response, "Retry save", status_code=503)
        self.assertEqual(
            self.client.post("/assessments/save/", {"calculation": token}).status_code, 302
        )

    def test_post_and_csrf_required_and_missing_record_is_404(self):
        from uuid import uuid4

        self.assertEqual(self.client.get("/assessments/save/").status_code, 405)
        self.assertEqual(
            Client(enforce_csrf_checks=True)
            .post("/assessments/save/", {"calculation": "invalid"})
            .status_code,
            403,
        )
        self.assertEqual(self.client.get(f"/assessments/{uuid4()}/").status_code, 404)

    def test_unchanged_saved_scenario_does_not_become_stale_overnight(self):
        from datetime import date

        with patch(
            "farmcredit.interfaces.web.views.timezone.localdate", return_value=date(2026, 10, 6)
        ):
            _, token = self.calculate(price_per_kg="30")
        saved = self.client.post("/assessments/save/", {"calculation": token})
        reference = saved.url.strip("/").split("/")[-1]
        with patch(
            "farmcredit.interfaces.web.views.timezone.localdate", return_value=date(2026, 10, 7)
        ):
            response, _ = self.calculate(reference=reference, price_per_kg="30")
        self.assertContains(response, "Current inputs, sources and policy match")

    def test_saved_source_text_is_escaped(self):
        from farmcredit.adapters.demo import load_monthly_evidence

        records = load_monthly_evidence()
        with patch(
            "farmcredit.interfaces.web.views.load_monthly_evidence",
            return_value=(
                replace(records[0], source="<script>alert('source')</script>"),
                *records[1:],
            ),
        ):
            _, token = self.calculate()
        saved = self.client.post("/assessments/save/", {"calculation": token})
        response = self.client.get(saved.url)
        self.assertContains(response, "&lt;script&gt;")
        self.assertNotContains(response, "<script>alert")


@override_settings(
    ROOT_URLCONF="legacy_urls",
    ALLOWED_HOSTS=["testserver"],
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class OfficerReviewWebTests(AuthenticatedWebTests):
    def setUp(self):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Permission
        from django.contrib.contenttypes.models import ContentType

        super().setUp()
        model = get_user_model()
        model.objects.all().delete()
        self.officer = model.objects.create_user(
            "officer",
            password=self.password,
            first_name="Test Officer",
        )
        permission, _ = Permission.objects.get_or_create(
            content_type=ContentType.objects.get_for_model(model),
            codename="review_assessment",
            defaults={"name": "Can review advisory"},
        )
        self.officer.user_permissions.add(permission)
        self.other = model.objects.create_user("reader", password=self.password)
        self.client.force_login(self.officer)
        _, token = SavedAssessmentWebTests.calculate(self)
        self.detail_url = self.client.post("/assessments/save/", {"calculation": token}).url
        self.review_url = self.detail_url + "review/"
        self.client.logout()

    calculate = SavedAssessmentWebTests.calculate

    def review_token(self):
        import html
        import re

        response = self.client.get(self.detail_url)
        match = re.search(r'name="review_token" value="([^"]+)"', response.content.decode())
        return html.unescape(match.group(1)) if match else None

    def test_authentication_and_permission_are_required(self):
        self.assertEqual(self.client.post(self.review_url).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.review_url).status_code, 403)
        self.assertIsNone(self.review_token())

    def test_approval_uses_session_identity_and_is_retry_safe(self):
        self.client.force_login(self.officer)
        token = self.review_token()
        payload = {
            "review_token": token,
            "decision": "approved",
            "note": "Reviewed assumptions.",
            "officer_name": "Impersonated",
        }
        self.assertEqual(self.client.post(self.review_url, payload).status_code, 302)
        self.assertEqual(self.client.post(self.review_url, payload).status_code, 302)
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Advisory approved")
        self.assertContains(response, "Test Officer")
        self.assertNotContains(response, "Impersonated")
        self.assertIsNone(self.review_token())

    def test_stale_open_form_cannot_approve_after_input_change(self):
        self.client.force_login(self.officer)
        token = self.review_token()
        self.calculate(price_per_kg="30")
        response = self.client.post(
            self.review_url, {"review_token": token, "decision": "approved"}
        )
        self.assertContains(response, "stale", status_code=409)

    def test_invalid_submitted_inputs_also_invalidate_review(self):
        self.client.force_login(self.officer)
        token = self.review_token()
        self.calculate(price_per_kg="-1")
        self.assertEqual(
            self.client.post(
                self.review_url,
                {
                    "review_token": token,
                    "decision": "approved",
                },
            ).status_code,
            409,
        )

    def test_approval_becomes_historical_when_case_changes(self):
        self.client.force_login(self.officer)
        self.client.post(
            self.review_url, {"review_token": self.review_token(), "decision": "approved"}
        )
        self.calculate(harvest_reduction="30")
        self.assertContains(self.client.get(self.detail_url), "Historical review")

    def test_request_changes_requires_reason_and_preserves_it(self):
        self.client.force_login(self.officer)
        token = self.review_token()
        self.assertEqual(
            self.client.post(
                self.review_url,
                {
                    "review_token": token,
                    "decision": "changes_requested",
                },
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                self.review_url,
                {
                    "review_token": token,
                    "decision": "changes_requested",
                    "note": "Please confirm outside debt.",
                },
            ).status_code,
            302,
        )
        response = self.client.get(self.detail_url)
        self.assertContains(response, "Changes requested")
        self.assertContains(response, "Please confirm outside debt.")

    def test_wrong_officer_or_assessment_token_is_rejected(self):
        from uuid import uuid4

        from django.contrib.auth import get_user_model

        self.client.force_login(self.officer)
        token = self.review_token()
        self.assertEqual(
            self.client.post(
                f"/assessments/{uuid4()}/review/",
                {
                    "review_token": token,
                    "decision": "approved",
                },
            ).status_code,
            400,
        )
        other = get_user_model().objects.create_user(
            "second",
            password=self.password,
            first_name="Second Officer",
        )
        other.user_permissions.set(self.officer.user_permissions.all())
        self.client.force_login(other)
        self.assertEqual(
            self.client.post(
                self.review_url,
                {
                    "review_token": token,
                    "decision": "approved",
                },
            ).status_code,
            400,
        )

    def test_csrf_and_post_are_required(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.officer)
        self.assertEqual(client.post(self.review_url, {"decision": "approved"}).status_code, 403)
        self.assertEqual(client.get(self.review_url).status_code, 405)

    def test_real_login_and_logout(self):
        response = self.client.post(
            "/accounts/login/",
            {
                "username": "officer",
                "password": self.password,
                "next": self.detail_url,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(self.review_token())
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 302)
        self.assertIsNone(self.review_token())

    def test_createofficer_requires_name_and_strong_password(self):
        from django.contrib.auth import get_user_model
        from django.core.management import call_command

        with patch(
            "farmcredit.interfaces.web.management.commands.createofficer.getpass",
            return_value=self.password,
        ):
            call_command("createofficer", "new-officer", name="Named Officer", verbosity=0)
        user = get_user_model().objects.get(username="new-officer")
        self.assertEqual(user.get_full_name(), "Named Officer")
        self.assertTrue(user.has_perm("auth.review_assessment"))
        self.assertTrue(user.check_password(self.password))

    def test_revoked_permission_rejects_an_existing_review_form(self):
        self.client.force_login(self.officer)
        token = self.review_token()
        self.officer.user_permissions.clear()
        self.assertEqual(
            self.client.post(
                self.review_url,
                {
                    "review_token": token,
                    "decision": "approved",
                },
            ).status_code,
            403,
        )

    def test_named_account_is_required_even_with_permission(self):
        self.officer.first_name = ""
        self.officer.save()
        self.client.force_login(self.officer)
        self.assertIsNone(self.review_token())
        self.assertEqual(
            self.client.post(self.review_url, {"decision": "approved"}).status_code, 403
        )


@override_settings(ALLOWED_HOSTS=["testserver"], ROOT_URLCONF="legacy_urls")
class WorkspaceAccessTests(AuthenticatedWebTests):
    def test_anonymous_routes_cannot_read_or_write_case_data(self):
        from uuid import uuid4

        anonymous = Client()
        urls = [
            "/",
            "/assessments/",
            "/assessments/save/",
            f"/assessments/{uuid4()}/",
            f"/assessments/{uuid4()}/review/",
        ]
        with patch("farmcredit.interfaces.web.saved_views.AssessmentStore") as store:
            for url in urls:
                for method in (anonymous.get, anonymous.post):
                    with self.subTest(url=url, method=method.__name__):
                        response = method(url)
                        self.assertEqual(response.status_code, 302)
                        self.assertTrue(response.url.startswith("/accounts/login/?next="))
                        self.assertNotContains(response, "FC-001", status_code=302)
                        self.assertIn("no-store", response["Cache-Control"])
            store.assert_not_called()

    def test_expired_htmx_session_navigates_to_sign_in(self):
        response = Client().post("/?repayment_mode=monthly", HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 401)
        self.assertIn("/accounts/login/?next=", response["HX-Redirect"])
        self.assertIn("repayment_mode", response["HX-Redirect"])
        self.assertNotIn("Location", response)

    def test_login_redirects_safely_and_logout_revokes_access(self):
        self.client.logout()
        for target, expected in (
            ("/assessments/", "/assessments/"),
            ("https://untrusted.example/", "/applications/"),
            ("", "/applications/"),
        ):
            response = self.client.post(
                "/accounts/login/",
                {
                    "username": "workspace-reader",
                    "password": self.password,
                    "next": target,
                },
            )
            self.assertEqual(response.url, expected)
            self.assertEqual(self.client.get("/accounts/login/").url, "/applications/")
            self.assertEqual(self.client.post("/accounts/logout/").url, "/accounts/login/")
            self.assertEqual(self.client.get("/assessments/").status_code, 302)

    def test_invalid_login_does_not_reveal_workspace(self):
        response = Client().post(
            "/accounts/login/",
            {
                "username": "workspace-reader",
                "password": "wrong-password",
            },
        )
        self.assertContains(response, "Sign-in failed")
        self.assertNotContains(response, 'aria-label="Workspace sections"')
        self.assertNotContains(response, "FC-001")

    def test_new_views_require_authentication_by_default(self):
        from django.contrib.auth.models import AnonymousUser
        from django.http import HttpResponse
        from django.test import RequestFactory

        from farmcredit.interfaces.web.middleware import WorkspaceLoginRequiredMiddleware

        request = RequestFactory().get("/future-case-page/")
        request.user = AnonymousUser()
        response = WorkspaceLoginRequiredMiddleware(lambda request: HttpResponse()).process_view(
            request,
            lambda request: HttpResponse("private case"),
            (),
            {},
        )
        self.assertEqual(response.status_code, 302)

    def test_expired_mutations_return_to_readable_pages_after_login(self):
        from urllib.parse import parse_qs, urlsplit
        from uuid import uuid4

        assessment_id = uuid4()
        anonymous = Client()
        save = anonymous.post("/assessments/save/")
        review = anonymous.post(f"/assessments/{assessment_id}/review/")
        self.assertEqual(parse_qs(urlsplit(save.url).query)["next"], ["/"])
        self.assertEqual(
            parse_qs(urlsplit(review.url).query)["next"], [f"/assessments/{assessment_id}/"]
        )


class AssetVersionTests(TransactionTestCase):
    def test_asset_content_change_produces_a_new_url(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from farmcredit.interfaces.web.templatetags.assets import asset_url

        with TemporaryDirectory() as directory:
            asset = Path(directory) / "style.css"
            asset.write_text("body { color: red; }")
            with patch(
                "farmcredit.interfaces.web.templatetags.assets.finders.find",
                return_value=str(asset),
            ):
                first = asset_url("farmcredit/workspace.css")
                self.assertEqual(first, asset_url("farmcredit/workspace.css"))
                asset.write_text("body { color: green; }")
                self.assertNotEqual(first, asset_url("farmcredit/workspace.css"))

    def test_login_references_content_versioned_assets(self):
        from farmcredit.interfaces.web.templatetags.assets import asset_url

        response = self.client.get("/accounts/login/")
        self.assertContains(response, asset_url("farmcredit/workspace.css"))
        self.assertContains(response, asset_url("farmcredit/workspace.js"))
