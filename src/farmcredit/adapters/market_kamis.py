# SPDX-License-Identifier: AGPL-3.0-only
"""A bounded public KAMIS search; response rows, not filters, establish identity."""

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from farmcredit.application.saved_assessments import canonical_json, input_fingerprint
from farmcredit.domain.market import MarketQuote

SOURCE_URL = "https://kamis.kilimo.go.ke/site/market_search"
MARKET_CHOICES = (("Nakuru Wakulima", "Nakuru Wakulima — KAMIS dry maize"),)
HEADERS = (
    "Market",
    "Commodity",
    "Classification",
    "Grade",
    "Sex",
    "Wholesale",
    "Retail",
    "Supply Volume",
    "County",
    "Date",
)
MAX_BYTES = 1024 * 1024


class _PriceTable(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in {"th", "td"} and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in {"th", "td"} and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            self.rows.append(tuple(self.row))
            self.row = None


def search_url(as_of: date) -> str:
    return (
        SOURCE_URL
        + "?"
        + urlencode(
            {
                "county[]": "Nakuru",
                "market[]": "337",
                "product[]": "1",
                "start": (as_of - timedelta(days=90)).isoformat(),
                "end": as_of.isoformat(),
                "per_page": "100",
            }
        )
    )


def download_prices(url: str) -> str:
    with urlopen(
        Request(url, headers={"User-Agent": "FarmCredit-demo/0.1"}), timeout=10
    ) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("KAMIS response exceeds the supported size.")
    return body.decode("utf-8")


def select_quote(html: str, *, market: str, as_of: date) -> MarketQuote | None:
    parser = _PriceTable()
    parser.feed(html)
    if HEADERS not in parser.rows:
        if "<h4>No Data</h4>" in html:
            return None
        raise ValueError("Unexpected KAMIS table format.")
    rows = parser.rows[parser.rows.index(HEADERS) + 1 :]
    candidates = []
    for cells in rows:
        if len(cells) != len(HEADERS):
            raise ValueError("Incomplete KAMIS price row.")
        row = dict(zip(HEADERS, cells))
        if (
            row["Market"] != market
            or row["County"] != "Nakuru"
            or row["Commodity"].lower() != "dry maize"
        ):
            continue
        observed = date.fromisoformat(row["Date"])
        if not as_of - timedelta(days=90) <= observed <= as_of or row["Wholesale"].strip() == "-":
            continue
        price = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)/(.+)", row["Wholesale"])
        if not price:
            raise ValueError("Unrecognised KAMIS price/unit.")
        candidates.append(
            MarketQuote(
                market,
                "Kenya / Nakuru",
                "Dry Maize",
                observed,
                Decimal(price[1]),
                price[2].upper(),
                "KES",
                "Wholesale",
                "published",
                classification=row["Classification"],
                grade=row["Grade"],
            )
        )
    if not candidates:
        return None
    latest = max(q.observed_on for q in candidates)
    quotes = {q for q in candidates if q.observed_on == latest}
    if len(quotes) != 1:
        raise ValueError("Multiple KAMIS prices or grades require clarification.")
    return quotes.pop()


def snapshot_kamis(market: str, *, as_of: date, retrieved_at: datetime) -> str:
    if market not in dict(MARKET_CHOICES):
        raise ValueError("Unsupported KAMIS reference market.")
    quote, error = None, None
    url = search_url(as_of)
    try:
        quote = select_quote(download_prices(url), market=market, as_of=as_of)
        if quote is None:
            error = "No matching Nakuru Wakulima wholesale dry-maize quote in the bounded 90-day KAMIS search. Other markets and retail prices were not substituted."
    except (OSError, ValueError, ArithmeticError, HTTPException):
        error = "KAMIS evidence unavailable: download or source validation failed. No price was substituted."
    payload = {
        "schema_version": 1,
        "market": market,
        "quote": quote,
        "error": error,
        "source": "Kenya Agricultural Market Information System (KAMIS), Ministry of Agriculture",
        "source_url": url,
        "download_url": url,
        "license": "Public price search; reuse licence not verified",
        "license_url": "",
        "period": "daily",
        "retrieved_at": retrieved_at.isoformat(),
        "as_of": as_of,
    }
    return canonical_json({**payload, "fingerprint": input_fingerprint(payload)})
