# SPDX-License-Identifier: AGPL-3.0-only
"""Strict arguments for internal tools; no model, framework or storage imports."""

from decimal import Decimal, InvalidOperation
from enum import Enum

from farmcredit.application.save_draft import CitedStatement, DraftRequest
from farmcredit.application.stress_scenarios import StressAssumptions

MAX_TOOL_CALLS = 12
MAX_RUN_SECONDS = 120


class ToolName(str, Enum):
    GET_CASE = "get_case"
    GET_RECORDS = "get_records"
    ASSESS_CASHFLOW = "assess_cashflow"
    SAVE_DRAFT = "save_draft"


def validate_arguments(tool: ToolName, arguments: dict) -> None:
    expected = {
        ToolName.GET_CASE: set(),
        ToolName.GET_RECORDS: {"categories"},
        ToolName.ASSESS_CASHFLOW: {"price_reduction", "harvest_reduction"},
        ToolName.SAVE_DRAFT: {
            "price_reduction",
            "harvest_reduction",
            "calculation_id",
            "statements",
            "questions",
        },
    }[tool]
    if not isinstance(arguments, dict) or set(arguments) != expected:
        raise ValueError("Tool arguments do not match the supported fields.")


def stress_assumptions(arguments: dict) -> StressAssumptions:
    values = [arguments[key] for key in ("price_reduction", "harvest_reduction")]
    if any(not isinstance(value, str) or len(value) > 20 for value in values):
        raise ValueError("Stress percentages must be exact decimal strings.")
    try:
        return StressAssumptions(*(Decimal(value) for value in values))
    except InvalidOperation as exception:
        raise ValueError("Invalid stress percentage.") from exception


def draft_request(arguments: dict, operation_id: str) -> DraftRequest:
    if not isinstance(arguments["statements"], list) or not isinstance(
        arguments["questions"], list
    ):
        raise ValueError("Statements and questions must be lists.")
    statements = []
    for item in arguments["statements"]:
        if (
            not isinstance(item, dict)
            or set(item) != {"text", "record_ids"}
            or not isinstance(item["record_ids"], list)
        ):
            raise ValueError("Each statement needs text and a list of record IDs.")
        statements.append(CitedStatement(item["text"], tuple(item["record_ids"])))
    return DraftRequest(
        operation_id,
        arguments["calculation_id"],
        stress_assumptions(arguments),
        tuple(statements),
        tuple(arguments["questions"]),
    )
