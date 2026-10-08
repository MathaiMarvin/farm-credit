# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded public download of WFP Kenya prices via HDX; no household data is sent."""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from http.client import HTTPException
from urllib.request import Request, urlopen

from farmcredit.application.saved_assessments import canonical_json, input_fingerprint
from farmcredit.domain.market import MarketQuote

SOURCE_URL = "https://data.humdata.org/dataset/wfp-food-prices-for-kenya"
DOWNLOAD_URL = "https://data.humdata.org/dataset/e0d3fba6-f9a2-45d7-b949-140c455197ff/resource/517ee1bf-2437-4f8c-aa1b-cb9925b9d437/download/wfp_food_prices_ken.csv"
LICENSE_URL = "https://creativecommons.org/licenses/by/3.0/igo/"
MAX_BYTES = 8 * 1024 * 1024


def download_prices() -> str:
    request = Request(DOWNLOAD_URL, headers={"User-Agent": "FarmCredit-demo/0.1"})
    with urlopen(request, timeout=10) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Price dataset exceeds the supported size.")
    return body.decode("utf-8-sig")


def select_quote(text: str, market: str, as_of: date, *, crop: str = "maize") -> MarketQuote | None:
    reader = csv.DictReader(io.StringIO(text))
    required = {
        "date",
        "market",
        "admin1",
        "admin2",
        "commodity",
        "currency",
        "unit",
        "price",
        "priceflag",
        "pricetype",
    }
    if not required <= set(reader.fieldnames or ()):
        raise ValueError("Unexpected price dataset format.")
    candidates = []
    for row in reader:
        if any(row.get(key) is None for key in required):
            raise ValueError("Incomplete price dataset row.")
        if (
            row["market"] != market
            or row["commodity"].casefold() != crop.strip().casefold()
            or row["pricetype"] != "Wholesale"
            or row["priceflag"] != "actual"
        ):
            continue
        observed = date.fromisoformat(row["date"])
        if observed > as_of:
            continue
        candidates.append(
            MarketQuote(
                market,
                f"Kenya / {row['admin1']} / {row['admin2']}",
                row["commodity"],
                observed,
                Decimal(row["price"]),
                row["unit"],
                row["currency"],
                row["pricetype"],
                row["priceflag"],
            )
        )
    if not candidates:
        return None
    latest = max(q.observed_on for q in candidates)
    quotes = set(q for q in candidates if q.observed_on == latest)
    if len(quotes) != 1:
        raise ValueError("Conflicting latest market observations.")
    return quotes.pop()


def snapshot_market(
    market: str | None, *, as_of: date, retrieved_at: datetime, crop: str = "maize"
) -> str:
    quote, error = None, None
    if market:
        try:
            quote = select_quote(download_prices(), market, as_of, crop=crop)
            if quote is None:
                error = "No matching actual wholesale observation for the recorded crop on or before the review date."
        except (OSError, ValueError, ArithmeticError, csv.Error, HTTPException):
            error = "Market evidence unavailable: download or source validation failed. No price was substituted."
    else:
        error = "No reference market selected. Request a dated buyer quote."
    payload = {
        "schema_version": 1,
        "market": market,
        "crop": crop,
        "quote": quote,
        "error": error,
        "source": "WFP Kenya Food Prices via HDX",
        "source_url": SOURCE_URL,
        "download_url": DOWNLOAD_URL,
        "license": "CC BY 3.0 IGO",
        "license_url": LICENSE_URL,
        "retrieved_at": retrieved_at.isoformat(),
        "as_of": as_of,
    }
    return canonical_json({**payload, "fingerprint": input_fingerprint(payload)})
