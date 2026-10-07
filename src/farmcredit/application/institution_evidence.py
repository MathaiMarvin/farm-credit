# SPDX-License-Identifier: AGPL-3.0-only
"""Restore a frozen institution file and review it without changing application inputs."""

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal

from farmcredit.application.saved_assessments import input_fingerprint
from farmcredit.domain.cashflow import CashMovement
from farmcredit.domain.institution import (
    InstitutionFile,
    InstitutionReview,
    ObligationRecord,
    RepaymentRecord,
    ReviewPolicy,
    SavingsRecord,
    YieldRecord,
    review_institution,
)

INSTITUTION_CATEGORIES = (
    "yield_history",
    "repayment_history",
    "savings",
    "current_obligations",
    "lender_policy",
)


@dataclass(frozen=True)
class InstitutionSource:
    record_id: str
    category: str
    values: dict
    source: str
    recorded_on: date
    basis: str = "observed"
    synthetic: bool = True


@dataclass(frozen=True)
class InstitutionAssessment:
    file: InstitutionFile
    policy: ReviewPolicy
    retrieved_at: str
    fingerprint: str
    sources: tuple[InstitutionSource, ...]
    review: InstitutionReview


def restore_institution(snapshot_json: str, *, expected_member: str | None):
    snapshot = json.loads(snapshot_json)
    if snapshot["schema_version"] != 1:
        raise ValueError("Unsupported institution snapshot schema.")
    body = {key: snapshot[key] for key in ("file", "policy")}
    if input_fingerprint(body) != snapshot["fingerprint"]:
        raise ValueError("Institution snapshot fingerprint mismatch.")
    data, rules = body["file"], body["policy"]
    if data["member_ref"] != expected_member:
        raise PermissionError("Institution file does not belong to the bound application.")
    file = InstitutionFile(
        data["member_ref"],
        data["version"],
        data["source"],
        date.fromisoformat(data["recorded_on"]),
        tuple(
            YieldRecord(
                r["record_id"],
                date.fromisoformat(r["harvested_on"]),
                Decimal(r["gross_kg"]),
                Decimal(r["area_hectares"]),
            )
            for r in data["yields"]
        )
        if data["yields"] is not None
        else None,
        tuple(
            RepaymentRecord(
                r["record_id"],
                date.fromisoformat(r["due_on"]),
                Decimal(r["due"]),
                Decimal(r["paid"]),
            )
            for r in data["repayments"]
        )
        if data["repayments"] is not None
        else None,
        SavingsRecord(
            data["savings"]["record_id"],
            Decimal(data["savings"]["balance"]),
            Decimal(data["savings"]["restricted"]),
        )
        if data["savings"] is not None
        else None,
        tuple(
            ObligationRecord(
                r["record_id"],
                r["cash_record_id"],
                date.fromisoformat(r["due_on"]),
                Decimal(r["amount"]),
            )
            for r in data["obligations"]
        )
        if data["obligations"] is not None
        else None,
        data["synthetic"],
    )
    policy = ReviewPolicy(
        rules["policy_id"],
        rules["version"],
        rules["source"],
        date.fromisoformat(rules["effective_on"]),
        tuple(rules["rules"]),
        rules["synthetic"],
    )
    retrieved = datetime.fromisoformat(snapshot["retrieved_at"])
    if retrieved.tzinfo is None:
        raise ValueError("Institution retrieval time must include a timezone.")
    return file, policy, snapshot


def institution_sources(file: InstitutionFile, policy: ReviewPolicy, *, as_of: date):
    sources = []
    if file.recorded_on <= as_of:
        for row in file.yields_or_empty:
            sources.append(
                InstitutionSource(
                    row.record_id,
                    "yield_history",
                    {
                        "harvested_on": row.harvested_on,
                        "crop": "maize",
                        "gross_kg": row.gross_kg,
                        "area_hectares": row.area_hectares,
                    },
                    file.source,
                    file.recorded_on,
                )
            )
        for row in file.repayments or ():
            sources.append(
                InstitutionSource(
                    row.record_id,
                    "repayment_history",
                    {"due_on": row.due_on, "due_kes": row.due, "paid_kes": row.paid},
                    file.source,
                    file.recorded_on,
                )
            )
        if file.savings:
            row = file.savings
            sources.append(
                InstitutionSource(
                    row.record_id,
                    "savings",
                    {
                        "balance_kes": row.balance,
                        "restricted_kes": row.restricted,
                        "unrestricted_kes": row.balance - row.restricted,
                    },
                    file.source,
                    file.recorded_on,
                )
            )
        for row in file.obligations or ():
            sources.append(
                InstitutionSource(
                    row.record_id,
                    "current_obligations",
                    {
                        "cash_record_id": row.cash_record_id,
                        "due_on": row.due_on,
                        "amount_kes": row.amount,
                    },
                    file.source,
                    file.recorded_on,
                )
            )
        if file.obligations == ():
            sources.append(
                InstitutionSource(
                    f"{file.member_ref}:obligations-coverage",
                    "current_obligations",
                    {
                        "recorded_obligation_count": 0,
                        "coverage": "Only this institution at the file recording date.",
                    },
                    file.source,
                    file.recorded_on,
                )
            )
    if policy.effective_on <= as_of:
        sources.append(
            InstitutionSource(
                f"{policy.policy_id}:{policy.version}",
                "lender_policy",
                {
                    "policy_id": policy.policy_id,
                    "version": policy.version,
                    "effective_on": policy.effective_on,
                    "rules": policy.rules,
                },
                policy.source,
                policy.effective_on,
                "declared",
            )
        )
    return tuple(sources)


def assess_institution(snapshot_json: str, inputs: dict, *, as_of: date) -> InstitutionAssessment:
    file, policy, snapshot = restore_institution(
        snapshot_json, expected_member=inputs.get("institution_record_set") or None
    )
    if file.recorded_on > as_of:
        file = replace(file, yields=None, repayments=None, savings=None, obligations=None)
    case = inputs["case"]
    movements = tuple(
        CashMovement(row["record_id"], date.fromisoformat(row["on"]), Decimal(row["amount"]))
        for row in case["other_movements"]
        if row.get("on") is not None and row.get("amount") is not None
    )
    review = review_institution(
        file,
        policy,
        as_of=as_of,
        starts_on=date.fromisoformat(case["starts_on"]) if case["starts_on"] else None,
        ends_on=date.fromisoformat(case["financing"]["repayment_on"])
        if case["financing"]["repayment_on"]
        else None,
        movements=movements,
    )
    return InstitutionAssessment(
        file,
        policy,
        snapshot["retrieved_at"],
        snapshot["fingerprint"],
        institution_sources(file, policy, as_of=as_of),
        review,
    )
