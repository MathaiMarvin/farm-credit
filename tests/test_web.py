# SPDX-License-Identifier: AGPL-3.0-only
"""Exercise the real form-to-calculation path without a database."""

import os
from dataclasses import replace
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "farmcredit.interfaces.web.settings")

import django

django.setup()

from django.contrib.staticfiles import finders
from django.test import Client, SimpleTestCase, override_settings

from farmcredit.adapters.demo import load_demo_evidence


@override_settings(ALLOWED_HOSTS=["testserver"])
class WorkspaceTests(SimpleTestCase):
    def test_packaged_assets_are_available(self):
        for asset in ("workspace.css", "workspace.js", "vendor/htmx.min.js", "vendor/htmx.LICENSE"):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(f"farmcredit/{asset}"))

    def test_initial_page_is_a_synthetic_case_not_an_assessment(self):
        response = self.client.get("/")
        self.assertContains(response, "Demo household FC-001")
        self.assertContains(response, "All records are synthetic")
        self.assertNotContains(response, "No shortfall in this scenario")
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Inspect input sources (34)")
        self.assertContains(response, "Synthetic cooperative planning worksheet")

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
        self.assertContains(response, "Monthly instalments · synthetic terms")
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


@override_settings(ALLOWED_HOSTS=["testserver"])
class SavedAssessmentWebTests(SimpleTestCase):
    def setUp(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        settings = override_settings(ASSESSMENT_DB=Path(self.directory.name) / "saved.sqlite3")
        settings.enable()
        self.addCleanup(settings.disable)

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
        with patch(
            "farmcredit.interfaces.web.saved_views.signing.loads",
            side_effect=signing.SignatureExpired,
        ):
            self.assertEqual(
                self.client.post("/assessments/save/", {"calculation": token}).status_code, 400
            )
        self.assertContains(self.client.get("/assessments/"), "No assessments saved yet")

    def test_invalid_calculation_has_no_save_action(self):
        response, token = self.calculate(price_per_kg="-1")
        self.assertIsNone(token)
        self.assertNotContains(response, 'id="save-assessment-form"')

    def test_save_failure_preserves_retry_token(self):
        import sqlite3

        _, token = self.calculate()
        with patch(
            "farmcredit.interfaces.web.saved_views.AssessmentStore.save",
            side_effect=sqlite3.OperationalError("unavailable"),
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
