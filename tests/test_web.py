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
            "/", {"received_on": "2027-10-15", "price_per_kg": "30"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "scenario:sale.price_per_kg")
        self.assertContains(response, "scenario:sale.received_on")
        self.assertContains(response, "Unsaved scenario edit; replaces demo:sale.price_per_kg")
        self.assertContains(response, "40 KES/kg")
        self.assertContains(response, "assumed")

    def test_missing_evidence_shows_a_gap_instead_of_a_result(self):
        with patch("farmcredit.interfaces.web.views.load_demo_evidence", return_value=()):
            response = self.client.post("/", {"received_on": "2027-09-10", "price_per_kg": "40"})
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
        response = self.client.post("/", {"received_on": "2027-09-10", "price_per_kg": "40"})
        self.assertContains(response, "No shortfall in this scenario")
        self.assertContains(response, "KSh 40,000.00")
        self.assertContains(response, "<!doctype html>")

    def test_htmx_submission_returns_partial_with_late_receipt_shortfall(self):
        response = self.client.post(
            "/", {"received_on": "2027-10-15", "price_per_kg": "40"}, HTTP_HX_REQUEST="true"
        )
        self.assertContains(response, "Repayment timing shortfall")
        self.assertContains(response, "KSh 20,000.00")
        self.assertContains(response, "Expected after the deadline")
        self.assertNotContains(response, "<!doctype html>")

    def test_changed_price_reaches_calculator(self):
        response = self.client.post("/", {"received_on": "2027-09-10", "price_per_kg": "10"})
        self.assertContains(response, "KSh 5,000.00")
        self.assertContains(response, "Repayment timing shortfall")

    def test_invalid_inputs_return_errors_without_result(self):
        for inputs in (
            {},
            {"received_on": "invalid", "price_per_kg": "40"},
            {"received_on": "2027-09-10", "price_per_kg": "-1"},
            {"received_on": "2027-09-10", "price_per_kg": "NaN"},
        ):
            with self.subTest(inputs=inputs):
                response = self.client.post("/", inputs, HTTP_HX_REQUEST="true")
                self.assertContains(response, "We need a correction")
                self.assertNotContains(response, 'id="result-summary"')

    def test_unsupported_dates_show_domain_error(self):
        for receipt, expected in (("2027-08-01", "Pre-harvest"), ("2027-09-30", "ordering")):
            with self.subTest(receipt=receipt):
                response = self.client.post("/", {"received_on": receipt, "price_per_kg": "40"})
                self.assertContains(response, expected)
                self.assertNotContains(response, 'id="result-summary"')

    def test_csrf_is_required_and_valid_token_is_accepted(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(client.post("/", {"received_on": "2027-09-10"}).status_code, 403)
        client.get("/")
        response = client.post(
            "/",
            {
                "received_on": "2027-09-10",
                "price_per_kg": "40",
                "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            },
        )
        self.assertContains(response, "No shortfall in this scenario")

    def test_unknown_routes_and_unsupported_methods_are_rejected(self):
        self.assertEqual(self.client.get("/unknown/").status_code, 404)
        self.assertEqual(self.client.delete("/").status_code, 405)
