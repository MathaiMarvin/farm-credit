# SPDX-License-Identifier: AGPL-3.0-only
from django.test import RequestFactory, SimpleTestCase

from farmcredit.interfaces.web.demo_views import guided_demo


class GuidedDemoTests(SimpleTestCase):
    def test_scenarios_use_cash_available_at_deadline(self):
        for scenario, amount in (("baseline", "40,000"), ("late", "20,000"), ("price", "34,000")):
            with self.subTest(scenario=scenario):
                response = guided_demo(RequestFactory().get("/demo/", {"scenario": scenario}))
                self.assertContains(response, f"KSh {amount}")
                self.assertContains(response, "Nothing here changes or saves an application")

    def test_fragment_and_reset(self):
        response = guided_demo(
            RequestFactory().get("/demo/", {"scenario": "baseline"}, HTTP_HX_REQUEST="true")
        )
        self.assertContains(response, "KSh 40,000 left after repayment")
        self.assertNotContains(response, "<html")
        self.assertContains(response, "10 Sep")

    def test_unknown_scenario_explains_fallback(self):
        response = guided_demo(RequestFactory().get("/demo/", {"scenario": "invalid"}))
        self.assertContains(response, "That scenario is unavailable")
        self.assertContains(response, "KSh 40,000 left after repayment")

    def test_mutation_not_allowed(self):
        self.assertEqual(guided_demo(RequestFactory().post("/demo/")).status_code, 405)
