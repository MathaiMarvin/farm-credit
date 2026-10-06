# SPDX-License-Identifier: AGPL-3.0-only
"""Portable immutable snapshots; no web or storage dependencies."""

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from farmcredit.application.stress_scenarios import StressAssumptions, StressComparison
from farmcredit.domain.evidence import EvidenceRecord
from farmcredit.domain.seasonal_case import SeasonalCase

POLICY_VERSION = "cashflow-schedules-v1"
SCHEMA_VERSION = 1


def _encode(value):
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported snapshot type: {type(value).__name__}")


def canonical_json(value) -> str:
    return json.dumps(
        value, default=_encode, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def input_snapshot(
    case: SeasonalCase,
    records: tuple[EvidenceRecord, ...],
    assumptions: StressAssumptions,
    mode: str,
) -> dict:
    return json.loads(
        canonical_json(
            {
                "case": case,
                "evidence": records,
                "assumptions": assumptions,
                "repayment_mode": mode,
                "policy_version": POLICY_VERSION,
            }
        )
    )


def input_fingerprint(inputs: dict) -> str:
    return hashlib.sha256(canonical_json(inputs).encode()).hexdigest()


def make_snapshot(inputs: dict, comparison: StressComparison) -> str:
    if comparison.baseline.issues or comparison.baseline.cashflow is None:
        raise ValueError("Only a completed calculation can be saved.")
    result = comparison.baseline.cashflow
    return canonical_json(
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": "FC-001",
            "inputs": inputs,
            "input_fingerprint": input_fingerprint(inputs),
            "result": result,
            "shortfalls": result.shortfalls,
            "scenarios": [
                {
                    "label": scenario.label,
                    "assumptions": scenario.assumptions,
                    "case": scenario.case,
                    "result": scenario.cashflow,
                    "error": scenario.error,
                    "shortfalls": scenario.cashflow.shortfalls if scenario.cashflow else (),
                }
                for scenario in comparison.scenarios
            ],
        }
    )


@dataclass(frozen=True)
class SavedAssessment:
    assessment_id: str
    case_id: str
    version: int
    saved_at: str
    snapshot_json: str

    @property
    def saved_on(self) -> datetime:
        return datetime.fromisoformat(self.saved_at)

    @property
    def snapshot(self) -> dict:
        # A fresh copy prevents a caller from changing this stored value in memory.
        return json.loads(self.snapshot_json)
