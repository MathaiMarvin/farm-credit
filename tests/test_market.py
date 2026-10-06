# SPDX-License-Identifier: AGPL-3.0-only
import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from farmcredit.adapters.market_hdx import MAX_BYTES, download_prices, select_quote, snapshot_market
from farmcredit.application.market_evidence import assess_market
from farmcredit.domain.market import MarketQuote, review_quote

HEADER = "date,admin1,admin2,market,commodity,unit,priceflag,pricetype,currency,price\n"
CSV = HEADER + "2022-04-15,Rift Valley,Nakuru,Nakuru,Maize,KG,actual,Wholesale,KES,35.88\n"
AS_OF = date(2026, 10, 6)
NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)


class MarketTests(TestCase):
    def quote(self, **changes):
        return replace(
            MarketQuote(
                "Nakuru",
                "Kenya / Rift Valley / Nakuru",
                "Maize",
                AS_OF,
                Decimal("4500"),
                "90 KG",
                "KES",
                "Wholesale",
                "actual",
            ),
            **changes,
        )

    def test_unit_conversion_preserves_original_quote_and_wholesale_warning(self):
        quote = self.quote()
        result = review_quote(quote, as_of=AS_OF)
        self.assertEqual(result.price_per_kg, Decimal("50"))
        self.assertEqual(quote.price, Decimal("4500"))
        self.assertEqual(result.status, "context_only")
        self.assertIn("farm-gate", " ".join(result.findings))
        self.assertTrue(result.questions)

    def test_stale_and_fresh_boundary_are_explicit(self):
        self.assertEqual(
            review_quote(self.quote(observed_on=date(2026, 7, 8)), as_of=AS_OF).status,
            "context_only",
        )
        self.assertEqual(
            review_quote(self.quote(observed_on=date(2026, 7, 7)), as_of=AS_OF).status, "stale"
        )

    def test_unknown_unit_currency_and_future_are_not_usable(self):
        for quote in (
            self.quote(unit="bag"),
            self.quote(currency="USD"),
            self.quote(observed_on=date(2026, 10, 7)),
        ):
            self.assertIsNone(review_quote(quote, as_of=AS_OF).price_per_kg)

    def test_invalid_prices_rejected(self):
        for value in ("NaN", "Infinity", "-1", "0"):
            with self.assertRaises(ValueError):
                self.quote(price=Decimal(value))

    def test_parser_uses_only_exact_market_commodity_type_and_actual_observations(self):
        text = (
            CSV
            + "2026-09-15,Rift Valley,Nakuru,Nakuru,Maize,KG,actual,Retail,KES,90\n"
            + "2026-09-15,Rift Valley,Nakuru,Nakuru,Maize flour,KG,actual,Wholesale,KES,100\n"
            + "2026-09-15,Rift Valley,Nakuru,Nakuru,Maize,KG,forecast,Wholesale,KES,80\n"
            + "2027-01-15,Rift Valley,Nakuru,Nakuru,Maize,KG,actual,Wholesale,KES,120\n"
        )
        self.assertEqual(select_quote(text, "Nakuru", AS_OF).price, Decimal("35.88"))
        self.assertIsNone(select_quote(text, "Other", AS_OF))

    def test_ambiguous_latest_records_and_changed_schema_rejected(self):
        for text in (
            CSV + CSV.splitlines()[1].replace("35.88", "40") + "\n",
            "<html>Error</html>",
            HEADER + "2026-09-15,Rift Valley,Nakuru,Nakuru,Maize,KG,actual,Wholesale,KES\n",
        ):
            with self.assertRaises(ValueError):
                select_quote(text, "Nakuru", AS_OF)

    def test_timeout_and_missing_records_are_explicit_not_zero(self):
        for outcome in (TimeoutError("private failure"), None):
            with patch(
                "farmcredit.adapters.market_hdx.download_prices",
                side_effect=outcome,
                return_value=HEADER,
            ):
                result = json.loads(snapshot_market("Nakuru", as_of=AS_OF, retrieved_at=NOW))
            self.assertIsNone(result["quote"])
            self.assertTrue(result["error"])
            self.assertNotIn("private failure", result["error"])

    def test_unselected_market_does_not_download(self):
        with patch("farmcredit.adapters.market_hdx.download_prices") as download:
            result = json.loads(snapshot_market(None, as_of=AS_OF, retrieved_at=NOW))
        download.assert_not_called()
        self.assertIsNone(result["quote"])

    def test_download_is_bounded(self):
        with patch("farmcredit.adapters.market_hdx.urlopen") as request:
            request.return_value.__enter__.return_value.read.return_value = b"x" * (MAX_BYTES + 1)
            with self.assertRaises(ValueError):
                download_prices()
            self.assertEqual(request.call_args.kwargs["timeout"], 10)

    def test_snapshot_retains_attribution_and_rejects_tampering_and_wrong_market(self):
        with patch("farmcredit.adapters.market_hdx.download_prices", return_value=CSV):
            frozen = snapshot_market("Nakuru", as_of=AS_OF, retrieved_at=NOW)
        inputs = {
            "context": {"market_reference": "Nakuru"},
            "case": {"sale": {"price_per_kg": "60"}},
        }
        result = assess_market(frozen, inputs, as_of=AS_OF)
        self.assertEqual(result.assumed_price_per_kg, "60")
        self.assertEqual(result.review.status, "stale")
        self.assertFalse(result.sources[0].synthetic)
        self.assertEqual(result.license, "CC BY 3.0 IGO")
        with self.assertRaises(ValueError):
            assess_market(frozen.replace("35.88", "1.00"), inputs, as_of=AS_OF)
        inputs["context"]["market_reference"] = None
        with self.assertRaises(ValueError):
            assess_market(frozen, inputs, as_of=AS_OF)
