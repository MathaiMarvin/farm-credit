# SPDX-License-Identifier: AGPL-3.0-only
"""Incomplete intake snapshots; no dependency on forms, storage or providers."""

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from farmcredit.application.saved_assessments import POLICY_VERSION, canonical_json
from farmcredit.domain.evidence import EvidenceBasis, EvidenceRecord, InputValue

# Field path, unit, officer-facing label. None always means unknown.
INTAKE_FIELDS = (
    ("starts_on", "date", "Assessment start date"),
    ("opening_cash", "KES", "Available opening cash (KSh)"),
    ("coverage_through", "date", "Household cash records confirmed through"),
    ("sale.harvest_on", "date", "Expected harvest date"),
    ("sale.received_on", "date", "Expected sale receipt date"),
    ("sale.gross_kg", "kg", "Expected gross harvest (kg)"),
    ("sale.retained_kg", "kg", "Harvest retained for food or seed (kg)"),
    ("sale.lost_kg", "kg", "Expected harvest losses (kg)"),
    ("sale.price_per_kg", "KES/kg", "Assumed sale price (KSh/kg)"),
    ("financing.supplied_on", "date", "Input supply date"),
    ("financing.principal", "KES", "Requested supplier financing (KSh)"),
    ("financing.charges", "KES", "Supplied financing charges (KSh)"),
)


@dataclass(frozen=True)
class SavedApplication:
    application_id: str
    case_id: str
    version: int
    saved_at: str
    snapshot_json: str
    assessment_id: None = None

    @property
    def snapshot(self) -> dict:
        return json.loads(self.snapshot_json)


def parse_movements(text: str, *, repayments: bool) -> list[dict]:
    """Explicit dated amounts, never generated interest or inferred instalments."""
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record_id, on, amount = (part.strip() for part in line.split(","))
            value = Decimal(amount)
            if not value.is_finite() or value != value.quantize(Decimal("0.01")):
                raise ValueError
            if not record_id or len(record_id) > 100 or "/" in record_id:
                raise ValueError
            if repayments and value <= 0:
                raise ValueError
            if any(row["record_id"] == record_id for row in rows):
                raise ValueError
            rows.append(
                {
                    "record_id": record_id,
                    "on": date.fromisoformat(on),
                    "amount": -value if repayments else value,
                }
            )
        except (ValueError, InvalidOperation):
            raise ValueError(
                "Use unique record ID, YYYY-MM-DD, amount on each line; repayments must be positive and amounts have at most two decimal places."
            ) from None
    if len(rows) > 60:
        raise ValueError("Supply at most 60 dated records per group.")
    return rows


def intake_inputs(data: dict) -> dict:
    context = {
        key: data.get(key) or None
        for key in (
            "farmer",
            "farm",
            "location",
            "season",
            "crop",
            "area_hectares",
            "available_records",
        )
    }
    context.update(
        weather_reference=data.get("weather_reference") or None,
        market_reference=data.get("market_reference") or None,
        kamis_market_reference=data.get("kamis_market_reference") or None,
        institution="Demo cooperative",
        institution_record_set=data.get("institution_record_set") or None,
        synthetic=True,
        financing_method="supplier",
        collection_method=data.get("collection_method") or None,
    )
    case = {"sale": {"record_id": "harvest-sale"}, "financing": {"record_id": "supplier-credit"}}
    records = []

    def evidence(field, value, unit):
        if value is not None and all(data.get(key) for key in ("source", "recorded_on", "basis")):
            records.append(
                EvidenceRecord(
                    f"intake:{field}",
                    InputValue(field, value, unit),
                    data["source"],
                    data["recorded_on"],
                    EvidenceBasis(data["basis"]),
                    True,
                )
            )

    for field, unit, _ in INTAKE_FIELDS:
        value = data.get(field.replace(".", "_"))
        parts = field.split(".")
        target = case if len(parts) == 1 else case[parts[0]]
        target[parts[-1]] = value
        evidence(field, value, unit)
    schedule = parse_movements(data.get("schedule", ""), repayments=True)
    if data["repayment_mode"] == "seasonal" and len(schedule) > 1:
        raise ValueError(
            "A seasonal schedule has one payment; select supplied instalments for several."
        )
    movements = parse_movements(data.get("cash_records", ""), repayments=False)
    ids = [item["record_id"] for item in schedule + movements] + ["harvest-sale", "supplier-credit"]
    if len(set(ids)) != len(ids):
        raise ValueError(
            "Record IDs must be distinct across repayments, cash records and generated sale/credit records."
        )
    end = max((row["on"] for row in schedule), default=None)
    case["financing"].update(
        schedule=schedule,
        repayment_on=end,
        schedule_source=data.get("schedule_source", ""),
        schedule_version=data.get("schedule_version", ""),
    )
    case["other_movements"] = movements
    evidence("financing.repayment_on", end, "date")
    for prefix, rows in (("cash", movements), ("repayment", schedule)):
        for row in rows:
            for key, unit in (("on", "date"), ("amount", "KES")):
                evidence(f"{prefix}/{row['record_id']}/{key}", row[key], unit)
    return json.loads(
        canonical_json(
            {
                "institution_record_set": data.get("institution_record_set") or None,
                "case": case,
                "context": context,
                "evidence": records,
                "repayment_mode": data["repayment_mode"],
                "policy_version": POLICY_VERSION,
                "intake": data,
            }
        )
    )


def intake_label(field: str) -> str:
    labels = {path: label for path, _, label in INTAKE_FIELDS}
    labels.update(
        farmer="Household reference",
        farm="Farm / plot reference",
        location="Farm location",
        season="Season",
        area_hectares="Plot area",
        crop="Crop",
    )
    labels.update(
        {
            "institution.arrears": "Recorded arrears",
            "institution.obligations": "Current institutional obligations",
        }
    )
    labels["financing.repayment_on"] = "Supplied repayment schedule"
    if field in labels:
        return labels[field]
    return (
        field.removeprefix("cash/")
        .removeprefix("repayment/")
        .replace("/on", " / date")
        .replace("/amount", " / amount")
        .replace("-", " ")
        .capitalize()
    )
