# SPDX-License-Identifier: AGPL-3.0-only
"""Price comparability is deterministic; quotations never replace sale assumptions."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

# Demo evidence-review convention, not a lender rule or validated market model.
MAX_PRICE_AGE_DAYS = 90


@dataclass(frozen=True)
class MarketQuote:
    market: str
    geography: str
    commodity: str
    observed_on: date
    price: Decimal
    unit: str
    currency: str
    price_type: str
    price_flag: str
    classification: str | None = None
    grade: str | None = None

    def __post_init__(self):
        if not self.price.is_finite() or self.price <= 0:
            raise ValueError("Market price must be finite and positive.")


@dataclass(frozen=True)
class MarketReview:
    status: str
    price_per_kg: Decimal | None
    findings: tuple[str, ...]
    questions: tuple[str, ...]


def review_quote(quote: MarketQuote, *, as_of: date) -> MarketReview:
    findings = []
    questions = []
    divisor = {"KG": Decimal(1), "90 KG": Decimal(90)}.get(quote.unit)
    comparable = divisor is not None and quote.currency == "KES"
    normalized = quote.price / divisor if comparable else None
    if quote.observed_on > as_of:
        status = "future"
        normalized = None
        findings.append("The observation date is after this investigation's review date.")
    elif not comparable:
        status = "incompatible"
        findings.append("The currency or unit is unsupported; no conversion was made.")
    elif (as_of - quote.observed_on).days > MAX_PRICE_AGE_DAYS:
        status = "stale"
        findings.append("Historical price only: older than the demo's 90-day freshness limit.")
    else:
        status = "context_only"
        findings.append(
            "Within the demo's 90-day freshness limit; this is not a future price forecast."
        )
    if status != "context_only":
        questions.append("Obtain a current, dated maize buyer quote for the proposed sale market.")
    findings.append(
        f"{quote.price_type} market evidence is not a confirmed farm-gate receipt. The officer's sale assumption is unchanged."
    )
    questions.append(
        "Confirm the buyer, maize grade, sale location, price basis, and transport/selling costs before using a market quote in a separate scenario."
    )
    return MarketReview(status, normalized, tuple(findings), tuple(questions))
