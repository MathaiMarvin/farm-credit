# SPDX-License-Identifier: AGPL-3.0-only
"""Restore a run's frozen market evidence, retaining the original sale assumption."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from farmcredit.application.institution_evidence import InstitutionSource
from farmcredit.application.saved_assessments import input_fingerprint
from farmcredit.domain.market import MarketQuote, MarketReview, review_quote


@dataclass(frozen=True)
class MarketAssessment:
    market: str | None
    quote: MarketQuote | None
    review: MarketReview
    assumed_price_per_kg: str | None
    retrieved_at: str
    source: str
    source_url: str
    license: str
    license_url: str
    fingerprint: str
    sources: tuple[InstitutionSource, ...]
    period: str = "monthly"


def assess_market(
    snapshot_json: str, inputs: dict, *, as_of: date, reference_field: str = "market_reference"
) -> MarketAssessment:
    snapshot = json.loads(snapshot_json)
    fingerprint = snapshot.pop("fingerprint")
    if snapshot["schema_version"] != 1 or input_fingerprint(snapshot) != fingerprint:
        raise ValueError("Invalid market evidence snapshot.")
    if snapshot["as_of"] != as_of.isoformat() or snapshot["market"] != inputs.get(
        "context", {}
    ).get(reference_field):
        raise ValueError("Market evidence does not match the application and review date.")
    if datetime.fromisoformat(snapshot["retrieved_at"]).tzinfo is None:
        raise ValueError("Market retrieval requires a timezone.")
    crop = inputs.get("context", {}).get("crop", "maize")
    if snapshot.get("crop", "maize").casefold() != crop.casefold():
        raise ValueError("Market evidence belongs to a different crop.")
    if reference_field == "kamis_market_reference" and "county" in snapshot:
        context = inputs.get("context", {})
        county = context.get("kamis_county") or (
            "Nakuru" if snapshot["market"] == "Nakuru Wakulima" else ""
        )
        if (
            snapshot["county"].casefold() != county.casefold()
            or (snapshot.get("classification") or "").casefold()
            != (context.get("kamis_classification") or "").casefold()
        ):
            raise ValueError("KAMIS evidence does not match the county and variety selection.")
    row = snapshot["quote"]
    quote = (
        MarketQuote(
            **{
                **row,
                "observed_on": date.fromisoformat(row["observed_on"]),
                "price": Decimal(row["price"]),
            }
        )
        if row
        else None
    )
    review = (
        review_quote(quote, as_of=as_of)
        if quote
        else MarketReview(
            "unavailable",
            None,
            (snapshot["error"],),
            ("Obtain a current, dated buyer quote for the proposed sale market.",),
        )
    )
    sources = (
        (
            InstitutionSource(
                "market:" + fingerprint,
                "kamis_prices" if reference_field == "kamis_market_reference" else "market_prices",
                row,
                snapshot["source"],
                quote.observed_on,
                "observed",
                False,
            ),
        )
        if quote
        else ()
    )
    return MarketAssessment(
        snapshot["market"],
        quote,
        review,
        inputs["case"]["sale"]["price_per_kg"],
        snapshot["retrieved_at"],
        snapshot["source"],
        snapshot["source_url"],
        snapshot["license"],
        snapshot["license_url"],
        fingerprint,
        sources,
        snapshot.get("period", "monthly"),
    )
