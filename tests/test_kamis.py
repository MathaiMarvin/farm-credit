# SPDX-License-Identifier: AGPL-3.0-only
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch

from farmcredit.adapters.market_kamis import HEADERS, select_quote, snapshot_kamis

AS_OF = date(2026, 10, 6)
ROW = (
    "Nakuru Wakulima",
    "Dry Maize",
    "White Maize",
    "-",
    "-",
    "45.00/Kg",
    "50.00/Kg",
    "1000",
    "Nakuru",
    "2026-10-05",
)


def table(*rows):
    return (
        "<table><tr>"
        + "".join(f"<th>{v}</th>" for v in HEADERS)
        + "</tr>"
        + "".join("<tr>" + "".join(f"<td>{v}</td>" for v in row) + "</tr>" for row in rows)
        + "</table>"
    )


class KamisTests(TestCase):
    def test_price_type_unit_grade_and_date_are_preserved(self):
        quote = select_quote(table(ROW), market="Nakuru Wakulima", as_of=AS_OF)
        self.assertEqual(quote.price, Decimal("45"))
        self.assertEqual(quote.unit, "KG")
        self.assertEqual(quote.classification, "White Maize")
        self.assertEqual(quote.price_type, "Wholesale")

    def test_ignored_provider_filters_do_not_leak_other_markets(self):
        for index, value in (
            (0, "Ahero"),
            (1, "Maize Flour"),
            (8, "Kisumu"),
            (9, "2026-10-07"),
            (9, "2022-04-15"),
            (5, "-"),
        ):
            row = list(ROW)
            row[index] = value
            self.assertIsNone(select_quote(table(row), market="Nakuru Wakulima", as_of=AS_OF))

    def test_conflicting_grades_and_prices_are_not_arbitrarily_selected(self):
        row = list(ROW)
        row[2] = "Mixed-Traditional"
        with self.assertRaises(ValueError):
            select_quote(table(ROW, row), market="Nakuru Wakulima", as_of=AS_OF)

    def test_unknown_units_are_retained_and_malformed_responses_fail(self):
        row = list(ROW)
        row[5] = "45.00/Bag"
        self.assertEqual(
            select_quote(table(row), market="Nakuru Wakulima", as_of=AS_OF).unit, "BAG"
        )
        for html in (
            "<html>Login</html>",
            table(ROW[:-1]),
            table(ROW).replace("45.00/Kg", "unknown"),
        ):
            with self.assertRaises(ValueError):
                select_quote(html, market="Nakuru Wakulima", as_of=AS_OF)
        self.assertIsNone(select_quote("<h4>No Data</h4>", market="Nakuru Wakulima", as_of=AS_OF))

    def test_download_failure_preserves_attribution_without_a_price(self):
        with patch("farmcredit.adapters.market_kamis.download_prices", side_effect=TimeoutError()):
            frozen = json.loads(
                snapshot_kamis(
                    "Nakuru Wakulima", as_of=AS_OF, retrieved_at=datetime.now(timezone.utc)
                )
            )
        self.assertIsNone(frozen["quote"])
        self.assertEqual(frozen["period"], "daily")
        self.assertIn("not verified", frozen["license"])
        self.assertIn("unavailable", frozen["error"])
