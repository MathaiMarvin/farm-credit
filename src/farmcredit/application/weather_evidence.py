# SPDX-License-Identifier: AGPL-3.0-only
"""Restore and review the exact weather outcome captured for a saved application."""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from farmcredit.application.institution_evidence import InstitutionSource
from farmcredit.application.saved_assessments import input_fingerprint
from farmcredit.domain.weather import WeatherHour, WeatherReview, review_weather


@dataclass(frozen=True)
class WeatherAssessment:
    reference: str
    latitude: Decimal | None
    longitude: Decimal | None
    starts_on: date
    ends_on: date
    hours: tuple[WeatherHour, ...]
    review: WeatherReview
    retrieved_at: str
    source: str
    source_url: str
    license: str
    license_url: str
    server_package: str
    tool: str
    fingerprint: str
    sources: tuple[InstitutionSource, ...]


def assess_weather(snapshot_json: str, inputs: dict, *, as_of: date) -> WeatherAssessment:
    snapshot = json.loads(snapshot_json)
    fingerprint = snapshot.pop("fingerprint")
    if (
        snapshot["schema_version"] != 1
        or input_fingerprint(snapshot) != fingerprint
        or snapshot["reference"] != inputs.get("context", {}).get("weather_reference")
        or snapshot["as_of"] != as_of.isoformat()
    ):
        raise ValueError("Weather evidence does not match this application and review date.")
    if datetime.fromisoformat(snapshot["retrieved_at"]).tzinfo is None:
        raise ValueError("Weather retrieval requires a timezone.")
    latitude, longitude, hours = None, None, ()
    raw, error = snapshot["raw"], snapshot["error"]
    if raw is None and not error:
        raise ValueError("Weather outcome lacks data and an explicit failure reason.")
    status = "unavailable"
    if raw is not None:
        try:
            if (
                raw["city"] != snapshot["reference"]
                or raw["start_date"] != as_of.isoformat()
                or raw["end_date"] != (as_of + timedelta(days=6)).isoformat()
            ):
                raise ValueError("Returned weather location or period does not match the request.")
            latitude, longitude = Decimal(str(raw["latitude"])), Decimal(str(raw["longitude"]))
            hours = tuple(
                WeatherHour(
                    datetime.fromisoformat(row["time"]),
                    Decimal(str(row["temperature_c"]))
                    if row["temperature_c"] is not None
                    else None,
                    Decimal(str(row["precipitation_mm"]))
                    if row["precipitation_mm"] is not None
                    else None,
                )
                for row in raw["weather_data"]
            )
            case = inputs["case"]
            review = review_weather(
                latitude=latitude,
                longitude=longitude,
                hours=hours,
                as_of=as_of,
                season_start=date.fromisoformat(case["starts_on"]) if case["starts_on"] else None,
                season_end=date.fromisoformat(case["sale"]["harvest_on"])
                if case["sale"]["harvest_on"]
                else None,
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exception:
            status, error, hours = "invalid", str(exception), ()
            latitude, longitude = None, None
    if error:
        review = WeatherReview(
            status,
            None,
            None,
            (error,),
            (
                "Obtain weather evidence matching the farm location, assessment date and crop season; expected harvest remains unchanged.",
            ),
        )
    sources = (
        (
            InstitutionSource(
                "weather:" + fingerprint,
                "weather",
                {
                    "reference": snapshot["reference"],
                    "latitude": latitude,
                    "longitude": longitude,
                    "period_start": as_of,
                    "period_end": as_of + timedelta(days=6),
                    "forecast_precipitation_mm": review.total_precipitation_mm,
                    "forecast_maximum_temperature_c": review.maximum_temperature_c,
                },
                snapshot["source"],
                as_of,
                "model forecast",
                False,
            ),
        )
        if hours
        else ()
    )
    return WeatherAssessment(
        snapshot["reference"],
        latitude,
        longitude,
        as_of,
        as_of + timedelta(days=6),
        hours,
        review,
        snapshot["retrieved_at"],
        snapshot["source"],
        snapshot["source_url"],
        snapshot["license"],
        snapshot["license_url"],
        snapshot["server_package"],
        snapshot["tool"],
        fingerprint,
        sources,
    )
