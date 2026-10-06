# SPDX-License-Identifier: AGPL-3.0-only
"""Validate short-range forecast coverage without inferring farm yield impacts."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class WeatherHour:
    at: datetime
    temperature_c: Decimal | None
    precipitation_mm: Decimal | None


@dataclass(frozen=True)
class WeatherReview:
    status: str
    total_precipitation_mm: Decimal | None
    maximum_temperature_c: Decimal | None
    findings: tuple[str, ...]
    questions: tuple[str, ...]


def review_weather(
    *,
    latitude: Decimal,
    longitude: Decimal,
    hours: tuple[WeatherHour, ...],
    as_of: date,
    season_start: date | None,
    season_end: date | None,
) -> WeatherReview:
    """The supported location is an explicitly selected Nakuru city reference."""
    if (
        not latitude.is_finite()
        or not longitude.is_finite()
        or abs(latitude - Decimal("-0.3031")) > Decimal("0.1")
        or abs(longitude - Decimal("36.0800")) > Decimal("0.1")
    ):
        raise ValueError("Returned coordinates do not match the selected Nakuru reference area.")
    expected = tuple(
        datetime.combine(as_of, datetime.min.time()) + timedelta(hours=i) for i in range(168)
    )
    if tuple(h.at for h in hours) != expected:
        raise ValueError("Forecast timestamps do not cover exactly the requested seven UTC days.")
    for hour in hours:
        for value in (hour.temperature_c, hour.precipitation_mm):
            if value is not None and not value.is_finite():
                raise ValueError("Weather values must be finite or explicitly unknown.")
        if hour.precipitation_mm is not None and hour.precipitation_mm < 0:
            raise ValueError("Precipitation cannot be negative.")
    complete = all(h.temperature_c is not None and h.precipitation_mm is not None for h in hours)
    findings = [
        "Short-range model forecast for the selected city reference, not a farm observation, seasonal outlook or yield estimate."
    ]
    questions = [
        "Confirm the farm location and crop-stage relevance with the officer; obtain appropriate seasonal evidence before changing harvest assumptions."
    ]
    covered = (
        season_start is not None
        and season_end is not None
        and as_of <= season_start <= season_end <= as_of + timedelta(days=6)
    )
    if not covered:
        findings.append(
            "The seven-day forecast does not cover the supplied season, or its dates are unknown. Expected harvest is unchanged."
        )
    if not complete:
        findings.append(
            "Some weather values are unknown. No complete-period total or temperature maximum was calculated."
        )
    return WeatherReview(
        "incomplete" if not complete else "context_only" if covered else "outside_season",
        sum((h.precipitation_mm for h in hours), Decimal(0)) if complete else None,
        max(h.temperature_c for h in hours) if complete else None,
        tuple(findings),
        tuple(questions),
    )
