# SPDX-License-Identifier: AGPL-3.0-only
"""Three explicitly synthetic member files and a versioned illustrative review policy."""

import json
from datetime import date, datetime
from decimal import Decimal

from farmcredit.application.institution_evidence import restore_institution
from farmcredit.application.saved_assessments import canonical_json, input_fingerprint
from farmcredit.domain.institution import (
    InstitutionFile,
    ObligationRecord,
    RepaymentRecord,
    ReviewPolicy,
    SavingsRecord,
    YieldRecord,
)

MEMBER_CHOICES = (
    ("DEMO-001", "Household A · complete institutional file"),
    ("DEMO-002", "Household B · recorded arrears"),
    ("DEMO-003", "Household C · missing repayment history"),
)

# Demo-only review rules, explicitly supplied in this fixture. No acceptance score,
# invented interest rate, lending threshold or institutional endorsement is implied.
DEMO_REVIEW_POLICY = ReviewPolicy(
    "demo-cooperative-review",
    "v1",
    "Synthetic demo cooperative review sheet; illustrative and not institution-validated",
    date(2026, 10, 5),
    ("repayment_history_required", "arrears_need_review", "obligations_must_reconcile"),
)


def load_member_file(member_ref: str | None) -> InstitutionFile:
    if member_ref is not None and member_ref not in dict(MEMBER_CHOICES):
        raise ValueError("Unknown synthetic institution file.")
    source = "Synthetic Demo cooperative member file"
    observed = date(2026, 10, 5)
    if not member_ref:
        return InstitutionFile(None, "demo-records-v1", source, observed, None, None, None, None)
    return InstitutionFile(
        member_ref,
        "demo-records-v1",
        source,
        observed,
        (
            YieldRecord(
                f"{member_ref}:yield-2024", date(2024, 9, 1), Decimal("1850"), Decimal("1")
            ),
            YieldRecord(
                f"{member_ref}:yield-2025", date(2025, 9, 1), Decimal("2100"), Decimal("1")
            ),
        ),
        None
        if member_ref == "DEMO-003"
        else (
            RepaymentRecord(
                f"{member_ref}:repayment-2025",
                date(2025, 10, 1),
                Decimal("18000"),
                Decimal("16500") if member_ref == "DEMO-002" else Decimal("18000"),
            ),
        ),
        SavingsRecord(f"{member_ref}:savings", Decimal("12000"), Decimal("10000")),
        (
            ObligationRecord(
                f"{member_ref}:existing-debt", "existing-debt", date(2027, 8, 15), Decimal("5000")
            ),
        ),
    )


def snapshot_institution(member_ref: str | None, *, retrieved_at: datetime) -> str:
    body = {"file": load_member_file(member_ref), "policy": DEMO_REVIEW_POLICY}
    return canonical_json(
        {
            "schema_version": 1,
            **body,
            "fingerprint": input_fingerprint(body),
            "retrieved_at": retrieved_at.isoformat(),
        }
    )


def policy_is_current(snapshot_json: str) -> bool:
    data = json.loads(snapshot_json)
    _, policy, _ = restore_institution(snapshot_json, expected_member=data["file"]["member_ref"])
    return canonical_json(policy) == canonical_json(DEMO_REVIEW_POLICY)


def demo_application_data(member_ref: str) -> dict:
    """Prefill a reviewable form; creating the application remains an explicit POST."""
    from farmcredit.adapters.demo import DEMO_RECORDED_ON, load_demo_case
    from farmcredit.application.intake import INTAKE_FIELDS

    if member_ref not in dict(MEMBER_CHOICES):
        raise ValueError("Unknown synthetic household.")
    case = load_demo_case()
    data = {
        "farmer": f"Synthetic household {member_ref}",
        "farm": f"Plot {member_ref}",
        "location": "Synthetic Nakuru plot",
        "season": "2027 maize",
        "crop": "maize",
        "area_hectares": "1",
        "repayment_mode": "seasonal",
        "institution_record_set": member_ref,
        "source": "Synthetic household planning worksheet; declared assumptions",
        "basis": "assumed",
        "recorded_on": DEMO_RECORDED_ON,
        "schedule_source": "Synthetic supplied cooperative schedule",
        "schedule_version": "demo-v1",
        "collection_method": "Supplied cash repayment",
    }
    for field, _, _ in INTAKE_FIELDS:
        value = case
        for part in field.split("."):
            value = getattr(value, part)
        data[field.replace(".", "_")] = value
    data["coverage_through"] = case.financing.repayment_on
    data["schedule"] = "\n".join(
        f"{row.record_id}, {row.on}, {-row.amount}" for row in case.financing.as_repayments()
    )
    data["cash_records"] = "\n".join(
        f"{row.record_id}, {row.on}, {row.amount}" for row in case.other_movements
    )
    return data
