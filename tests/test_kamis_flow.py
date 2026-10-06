# SPDX-License-Identifier: AGPL-3.0-only
import json
from unittest.mock import patch

import test_applications as fixtures
from django.test import TransactionTestCase
from django.urls import reverse
from test_kamis import ROW, table
from test_market import CSV

from farmcredit.adapters.institution_demo import demo_application_data
from farmcredit.adapters.persistence.models import Draft


class KamisFlowTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save
    investigate = fixtures.ApplicationTests.investigate

    def test_both_sources_are_independent_frozen_and_visible(self):
        saved = self.save(
            {
                **demo_application_data("DEMO-001"),
                "market_reference": "Nakuru",
                "kamis_market_reference": "Nakuru Wakulima",
            }
        )
        with (
            patch("farmcredit.adapters.market_hdx.download_prices", return_value=CSV) as wfp,
            patch(
                "farmcredit.adapters.market_kamis.download_prices", return_value=table(ROW)
            ) as kamis,
        ):
            result = self.investigate(saved)
        wfp.assert_called_once()
        kamis.assert_called_once()
        draft = json.loads(Draft.objects.get(pk=result["draft_id"]).snapshot_json)
        self.assertEqual(draft["market"]["quote"]["price"], "35.88")
        self.assertEqual(draft["kamis"]["quote"]["price"], "45")
        self.assertNotEqual(
            draft["market"]["sources"][0]["record_id"], draft["kamis"]["sources"][0]["record_id"]
        )
        self.assertEqual(
            draft["calculation"]["comparison"]["baseline"]["cashflow"]["cash_after_repayment"],
            "40000",
        )
        page = self.client.get(reverse("saved-draft", args=[result["draft_id"]]))
        self.assertContains(page, 'id="kamis-heading"')
        self.assertContains(page, "Observation date: 2026-10-05")
        self.assertContains(page, "Source month: 2022-04")

    def test_kamis_outage_does_not_discard_wfp_evidence(self):
        saved = self.save(
            {
                **demo_application_data("DEMO-001"),
                "market_reference": "Nakuru",
                "kamis_market_reference": "Nakuru Wakulima",
            }
        )
        with (
            patch("farmcredit.adapters.market_hdx.download_prices", return_value=CSV),
            patch("farmcredit.adapters.market_kamis.download_prices", side_effect=TimeoutError()),
        ):
            result = self.investigate(saved)
        draft = json.loads(Draft.objects.get(pk=result["draft_id"]).snapshot_json)
        self.assertEqual(draft["market"]["quote"]["price"], "35.88")
        self.assertIsNone(draft["kamis"]["quote"])
        self.assertEqual(draft["kamis"]["review"]["status"], "unavailable")
