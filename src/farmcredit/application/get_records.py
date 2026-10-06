# SPDX-License-Identifier: AGPL-3.0-only
"""Retrieve categorised evidence from an authorised immutable case brief."""

from dataclasses import dataclass
from enum import Enum

from farmcredit.application.get_case import CaseBrief
from farmcredit.application.institution_evidence import (
    INSTITUTION_CATEGORIES,
    InstitutionAssessment,
    InstitutionSource,
)
from farmcredit.application.market_evidence import MarketAssessment
from farmcredit.application.weather_evidence import WeatherAssessment
from farmcredit.domain.evidence import EvidenceIssue, EvidenceRecord
from farmcredit.domain.institution import InstitutionReview, ReviewPolicy


class RecordCategory(str, Enum):
    CASH_FLOW = "cash_flow"
    HARVEST = "harvest"
    CREDIT_TERMS = "credit_terms"
    REPAYMENT_SCHEDULE = "repayment_schedule"
    REPAYMENT_HISTORY = "repayment_history"
    YIELD_HISTORY = "yield_history"
    SAVINGS = "savings"
    CURRENT_OBLIGATIONS = "current_obligations"
    LENDER_POLICY = "lender_policy"
    MARKET_PRICES = "market_prices"
    KAMIS_PRICES = "kamis_prices"
    WEATHER = "weather"


class RecordStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INCOMPLETE = "incomplete"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class RecordGroup:
    category: RecordCategory
    status: RecordStatus
    records: tuple[EvidenceRecord | InstitutionSource, ...]
    gaps: tuple[EvidenceIssue, ...]
    explanation: str


@dataclass(frozen=True)
class CaseRecords:
    assessment_id: str | None
    case_id: str
    version: int
    groups: tuple[RecordGroup, ...]
    limitations: tuple[str, ...]
    application_id: str | None = None
    institution_review: InstitutionReview | None = None
    institution_policy: ReviewPolicy | None = None
    institution_fingerprint: str | None = None
    retrieved_at: str | None = None
    market: MarketAssessment | None = None
    kamis: MarketAssessment | None = None
    weather: WeatherAssessment | None = None


def _category(field: str) -> RecordCategory | None:
    if field.startswith("cash/") or field in {"starts_on", "opening_cash", "coverage_through"}:
        return RecordCategory.CASH_FLOW
    if field.startswith("sale."):
        return RecordCategory.HARVEST
    if field.startswith("repayment/") or field == "financing.repayment_on":
        return RecordCategory.REPAYMENT_SCHEDULE
    if field.startswith("financing."):
        return RecordCategory.CREDIT_TERMS
    return None


def get_records(
    brief: CaseBrief,
    categories: tuple[str, ...],
    *,
    institution: InstitutionAssessment | None = None,
    market: MarketAssessment | None = None,
    kamis: MarketAssessment | None = None,
    weather: WeatherAssessment | None = None,
) -> CaseRecords:
    """Availability means recorded evidence exists, not that it has been verified.

    Unknown categories are caller errors. Known categories with no captured
    evidence are explicitly unavailable; no external retrieval is implied.
    """
    if not isinstance(categories, (tuple, list)) or not categories:
        raise ValueError("Request at least one supported evidence category.")
    requested = tuple(RecordCategory(category) for category in categories)
    if len(set(requested)) != len(requested):
        raise ValueError("Request each evidence category only once.")
    groups = []
    for category in requested:
        if category == RecordCategory.WEATHER and weather is not None:
            groups.append(
                RecordGroup(
                    category,
                    RecordStatus.INCOMPLETE if weather.sources else RecordStatus.UNAVAILABLE,
                    weather.sources,
                    (),
                    " ".join(weather.review.findings),
                )
            )
            continue
        price_evidence = (
            market
            if category == RecordCategory.MARKET_PRICES
            else kamis
            if category == RecordCategory.KAMIS_PRICES
            else None
        )
        if price_evidence is not None:
            groups.append(
                RecordGroup(
                    category,
                    RecordStatus.INCOMPLETE if price_evidence.quote else RecordStatus.UNAVAILABLE,
                    price_evidence.sources,
                    (),
                    " ".join(price_evidence.review.findings),
                )
            )
            continue
        if category.value in INSTITUTION_CATEGORIES and institution is not None:
            sources = tuple(row for row in institution.sources if row.category == category.value)
            groups.append(
                RecordGroup(
                    category,
                    RecordStatus.AVAILABLE if sources else RecordStatus.UNAVAILABLE,
                    sources,
                    (),
                    "Synthetic recorded evidence; coverage is limited to the source recording date."
                    if sources
                    else "No usable institutional records for this category. Missing history or balances are not zero.",
                )
            )
            continue
        records = tuple(r for r in brief.sources if _category(r.input.field) == category)
        gaps = tuple(g for g in brief.gaps if _category(g.field) == category)
        if not records:
            status = RecordStatus.UNAVAILABLE
            explanation = "No source records for this category are captured in this saved version."
        elif any(g.reason == "conflicting sources" for g in gaps):
            status = RecordStatus.CONFLICTING
            explanation = "Sources disagree; officer clarification is required."
        elif gaps:
            status = RecordStatus.INCOMPLETE
            explanation = "Records exist but have unresolved evidence gaps."
        else:
            status = RecordStatus.AVAILABLE
            explanation = "Recorded sources are available; this does not establish their accuracy or freshness."
        groups.append(RecordGroup(category, status, records, gaps, explanation))
    return CaseRecords(
        brief.assessment_id,
        brief.case_id,
        brief.version,
        tuple(groups),
        brief.limitations,
        brief.application_id,
        institution.review if institution and RecordCategory.LENDER_POLICY in requested else None,
        institution.policy if institution and RecordCategory.LENDER_POLICY in requested else None,
        institution.fingerprint if institution else None,
        institution.retrieved_at if institution else None,
        market if RecordCategory.MARKET_PRICES in requested else None,
        kamis if RecordCategory.KAMIS_PRICES in requested else None,
        weather if RecordCategory.WEATHER in requested else None,
    )
