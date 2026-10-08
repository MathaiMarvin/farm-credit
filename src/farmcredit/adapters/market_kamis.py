# SPDX-License-Identifier: AGPL-3.0-only
"""A bounded public KAMIS search; response rows, not filters, establish identity."""

import json
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


def search_url(as_of: date, *, county="Nakuru", market_id="337", product_id="1") -> str:
    return (
        SOURCE_URL
        + "?"
        + urlencode(
            {
                "county[]": county,
                "market[]": market_id,
                "product[]": product_id,
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


def select_quote(
    html: str,
    *,
    market: str,
    as_of: date,
    county: str = "Nakuru",
    crop: str = "maize",
    classification: str | None = None,
) -> MarketQuote | None:
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
            or row["County"].casefold() != county.casefold()
            or row["Commodity"].casefold()
            != ("dry maize" if crop.casefold() == "maize" else crop.casefold())
        ):
            continue
        if classification and row["Classification"].casefold() != classification.casefold():
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
                f"Kenya / {row['County']}",
                row["Commodity"],
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
        options = "; ".join(sorted({f"{q.classification} (grade {q.grade})" for q in quotes})[:8])
        raise ValueError(
            "Multiple KAMIS prices or grades require clarification. Record the matching variety/classification: "
            + options
        )
    return quotes.pop()


class _Catalogue(HTMLParser):
    def __init__(self):
        super().__init__()
        self.select = None
        self.option = None
        self.options = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "select":
            self.select = attrs.get("name")
        elif tag == "option" and self.select:
            self.option = [attrs.get("value", ""), ""]

    def handle_data(self, data):
        if self.option is not None:
            self.option[1] += data

    def handle_endtag(self, tag):
        if tag == "option" and self.option is not None:
            value, label = self.option
            if value:
                self.options.setdefault(self.select, []).append((value, label.strip()))
            self.option = None
        elif tag == "select":
            self.select = None


def resolve_search(market: str, county: str, crop: str) -> tuple[str, str, str]:
    catalogue = _Catalogue()
    catalogue.feed(download_prices(SOURCE_URL))
    counties = [
        value
        for value, label in catalogue.options.get("county[]", [])
        if label.casefold() == county.casefold()
    ]
    commodity = "dry maize" if crop.casefold() == "maize" else crop.casefold()
    products = [
        value
        for value, label in catalogue.options.get("product[]", [])
        if label.casefold() == commodity
    ]
    if len(counties) != 1 or len(products) != 1:
        raise ValueError(
            "KAMIS needs an exact county and crop/variety from its catalogue; no alternative commodity was substituted."
        )
    markets_url = "https://kamis.kilimo.go.ke/index.php/site/county_markets?" + urlencode(
        {"counties[]": counties[0]}
    )
    markets = json.loads(download_prices(markets_url))
    if not isinstance(markets, list):
        raise ValueError("Unexpected KAMIS market catalogue.")
    matches = [
        str(row["id"])
        for row in markets
        if row.get("trade_point_name", "").casefold() == market.casefold()
    ]
    if len(matches) != 1 or not matches[0].isdigit() or not products[0].isdigit():
        raise ValueError(
            "KAMIS needs an exact market name in the selected county; no other market was substituted."
        )
    return counties[0], matches[0], products[0]


def snapshot_kamis(
    market: str,
    *,
    as_of: date,
    retrieved_at: datetime,
    crop: str = "maize",
    county: str | None = None,
    classification: str | None = None,
) -> str:
    county = county or ("Nakuru" if market == "Nakuru Wakulima" else "")
    quote, error = None, None
    url = SOURCE_URL
    try:
        if market == "Nakuru Wakulima" and county == "Nakuru" and crop.casefold() == "maize":
            url = search_url(as_of)
        else:
            if not county:
                raise ValueError("Record the KAMIS market county before requesting prices.")
            county, market_id, product_id = resolve_search(market, county, crop)
            url = search_url(as_of, county=county, market_id=market_id, product_id=product_id)
        quote = select_quote(
            download_prices(url),
            market=market,
            county=county,
            crop=crop,
            as_of=as_of,
            classification=classification,
        )
        if quote is None:
            error = "No matching wholesale quote for the recorded crop, county and market in the bounded 90-day KAMIS search. Other commodities, markets and retail prices were not substituted."
    except ValueError as exception:
        error = "KAMIS evidence unavailable: " + str(exception)
    except (OSError, ArithmeticError, HTTPException):
        error = "KAMIS evidence unavailable: download or source validation failed. No price was substituted."
    payload = {
        "schema_version": 1,
        "market": market,
        "crop": crop,
        "county": county,
        "classification": classification,
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
