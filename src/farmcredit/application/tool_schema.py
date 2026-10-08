# SPDX-License-Identifier: AGPL-3.0-only
"""Shared tool descriptions for model and MCP boundaries."""

from farmcredit.application.get_records import RecordCategory


def _object(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


STRING = {"type": "string"}
STRINGS = {"type": "array", "items": STRING}
STRESS = {
    key: {
        "type": "string",
        "maxLength": 20,
        "description": "Exact decimal percentage from 0 to 100.",
    }
    for key in ("price_reduction", "harvest_reduction")
}
FIELDS = {
    "get_case": {},
    "get_records": {
        "categories": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "enum": [category.value for category in RecordCategory]},
        }
    },
    "assess_cashflow": STRESS,
    "save_draft": {
        **STRESS,
        "calculation_id": {"type": ["string", "null"]},
        "statements": {"type": "array", "items": _object({"text": STRING, "record_ids": STRINGS})},
        "questions": STRINGS,
    },
}
DESCRIPTIONS = {
    "get_case": "Read the bound saved case, evidence gaps and provenance.",
    "get_records": "Read source groups: cash_flow, harvest, credit_terms, repayment_schedule, repayment_history, yield_history, savings, current_obligations, lender_policy, market_prices, kamis_prices, weather. Choose only the listed categories. institution_review is returned metadata, never a category. A null review or unavailable lender_policy means no linked policy; request it from the named institution. Supplied example institutional records are synthetic.",
    "assess_cashflow": "Calculate from saved evidence with explicit stress assumptions; missing evidence stays unknown.",
    "save_draft": "Save cited statements and questions for human review using a calculation from this run, or questions only with no calculation_id when a bound application has verified gaps. Ends the run; never approves credit.",
}
