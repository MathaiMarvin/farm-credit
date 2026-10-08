# SPDX-License-Identifier: AGPL-3.0-only
import json
from datetime import datetime, timezone
from unittest import TestCase
from unittest.mock import AsyncMock, patch

from test_kamis import AS_OF, ROW, table
from test_market import HEADER
from test_weather import TODAY, forecast

from farmcredit.adapters.market_hdx import select_quote as select_hdx
from farmcredit.adapters.market_kamis import resolve_search, select_quote, snapshot_kamis
from farmcredit.adapters.weather_mcp import snapshot_weather
from farmcredit.application.market_evidence import assess_market
from farmcredit.application.weather_evidence import assess_weather


class PortableEvidenceTests(TestCase):
    def test_rice_ahero_is_selected_without_accepting_maize_or_another_county(self):
        row = list(ROW)
        row[0], row[1], row[8] = "Ahero", "Rice", "Kisumu"
        quote = select_quote(
            table(ROW, row), market="Ahero", county="Kisumu", crop="rice", as_of=AS_OF
        )
        self.assertEqual(quote.commodity, "Rice")
        self.assertEqual(quote.geography, "Kenya / Kisumu")
        self.assertIsNone(
            select_quote(table(row), market="Ahero", county="Kisumu", crop="maize", as_of=AS_OF)
        )
        self.assertIsNone(
            select_quote(table(row), market="Ahero", county="Nakuru", crop="rice", as_of=AS_OF)
        )

    def test_kamis_resolves_published_ids_and_never_guesses_a_variety(self):
        catalogue = '<select name="county[]"><option value="Kisumu">Kisumu</option></select><select name="product[]"><option value="4">Rice</option></select>'
        markets = json.dumps([{"id": "234", "trade_point_name": "Ahero"}])
        with patch(
            "farmcredit.adapters.market_kamis.download_prices", side_effect=[catalogue, markets]
        ):
            self.assertEqual(resolve_search("Ahero", "Kisumu", "rice"), ("Kisumu", "234", "4"))
        with patch("farmcredit.adapters.market_kamis.download_prices", return_value=catalogue):
            with self.assertRaisesRegex(ValueError, "exact county and crop"):
                resolve_search("Ahero", "Kisumu", "beans")

    def test_frozen_market_evidence_cannot_be_reused_for_a_different_crop(self):
        with patch("farmcredit.adapters.market_kamis.download_prices", return_value=table(ROW)):
            snapshot = snapshot_kamis(
                "Nakuru Wakulima", as_of=AS_OF, retrieved_at=datetime.now(timezone.utc)
            )
        with self.assertRaisesRegex(ValueError, "different crop"):
            assess_market(
                snapshot,
                {"context": {"crop": "rice", "kamis_market_reference": "Nakuru Wakulima"}},
                as_of=AS_OF,
                reference_field="kamis_market_reference",
            )

    def test_hdx_matches_crop_as_well_as_market(self):
        text = HEADER + "2026-10-05,Nyanza,Kisumu,Kisumu,Rice,KG,actual,Wholesale,KES,130\n"
        self.assertIsNotNone(select_hdx(text, "Kisumu", AS_OF, crop="rice"))
        self.assertIsNone(select_hdx(text, "Kisumu", AS_OF, crop="maize"))

    def test_weather_matches_resolved_kisumu_not_nakuru(self):
        raw = forecast()
        raw.update(city="Kisumu", latitude=-0.1022, longitude=34.7617)
        inputs = {
            "context": {"weather_reference": "Kisumu"},
            "case": {"starts_on": None, "sale": {"harvest_on": None}},
        }
        location = {
            "name": "Kisumu",
            "latitude": -0.1022,
            "longitude": 34.7617,
            "country_code": "KE",
        }
        with (
            patch("farmcredit.adapters.weather_mcp.resolve_reference", return_value=location),
            patch("farmcredit.adapters.weather_mcp.fetch_weather", new=AsyncMock(return_value=raw)),
        ):
            snapshot = snapshot_weather(
                "Kisumu", as_of=TODAY, retrieved_at=datetime.now(timezone.utc)
            )
        self.assertTrue(assess_weather(snapshot, inputs, as_of=TODAY).hours)
        raw.update(latitude=-0.3031, longitude=36.0800)
        with (
            patch("farmcredit.adapters.weather_mcp.resolve_reference", return_value=location),
            patch("farmcredit.adapters.weather_mcp.fetch_weather", new=AsyncMock(return_value=raw)),
        ):
            snapshot = snapshot_weather(
                "Kisumu", as_of=TODAY, retrieved_at=datetime.now(timezone.utc)
            )
        self.assertEqual(assess_weather(snapshot, inputs, as_of=TODAY).review.status, "invalid")

    def test_variety_selection_resolves_real_price_ambiguity(self):
        first = list(ROW)
        first[0], first[1], first[2], first[8] = "Ahero", "Rice", "Pishori", "Kisumu"
        second = first.copy()
        second[2], second[5] = "Basmati", "60.00/Kg"
        with self.assertRaisesRegex(ValueError, "Pishori"):
            select_quote(
                table(first, second), market="Ahero", county="Kisumu", crop="rice", as_of=AS_OF
            )
        quote = select_quote(
            table(first, second),
            market="Ahero",
            county="Kisumu",
            crop="rice",
            classification="Pishori",
            as_of=AS_OF,
        )
        self.assertEqual(quote.classification, "Pishori")
        self.assertEqual(str(quote.price), "45.00")

    def test_model_record_schema_lists_only_real_categories(self):
        from farmcredit.application.get_records import RecordCategory
        from farmcredit.application.tool_schema import FIELDS

        categories = FIELDS["get_records"]["categories"]["items"]["enum"]
        self.assertCountEqual(categories, [category.value for category in RecordCategory])
        self.assertNotIn("institution_review", categories)
