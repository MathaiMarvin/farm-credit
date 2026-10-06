# SPDX-License-Identifier: AGPL-3.0-only
"""A fixed evidence check for intake; autonomous model selection is a later feature."""

from uuid import uuid4

from farmcredit.adapters.agent_runs import invoke_tool, start_run
from farmcredit.application.intake import intake_label


def investigate_application(*, application_id: str, officer_id: str) -> str:
    run_id = start_run(application_id=application_id, officer_id=officer_id)

    def call(tool, arguments):
        return invoke_tool(
            run_id=run_id,
            officer_id=officer_id,
            operation_id=str(uuid4()),
            tool=tool,
            arguments=arguments,
        )

    brief = call("get_case", {})
    if brief["status"] != "succeeded":
        return run_id
    records = call(
        "get_records",
        {
            "categories": [
                "cash_flow",
                "harvest",
                "credit_terms",
                "repayment_schedule",
                "repayment_history",
                "yield_history",
                "savings",
                "current_obligations",
                "lender_policy",
                "market_prices",
                "kamis_prices",
                "weather",
            ]
        },
    )
    if records["status"] != "succeeded":
        return run_id
    stress = {"price_reduction": "20", "harvest_reduction": "20"}
    market = records["result"].get("market")
    market_questions = market["review"]["questions"] if market else []
    kamis = records["result"].get("kamis")
    market_questions = list(
        dict.fromkeys([*market_questions, *(kamis["review"]["questions"] if kamis else [])])
    )
    weather = records["result"].get("weather")
    market_questions.extend(weather["review"]["questions"] if weather else [])
    gaps = brief["result"]["gaps"]
    institutional = records["result"].get("institution_review")
    institutional_questions = institutional["questions"] if institutional else []
    if gaps or (institutional and institutional["status"] != "checks_satisfied"):
        questions = list(
            dict.fromkeys(
                f"Please clarify {intake_label(g['field'])}: {g['reason']}." for g in gaps
            )
        )
        questions = list(dict.fromkeys([*questions, *institutional_questions, *market_questions]))[
            :30
        ]
        call(
            "save_draft",
            {**stress, "calculation_id": None, "statements": [], "questions": questions},
        )
        return run_id
    calculation = call("assess_cashflow", stress)
    if calculation["status"] != "succeeded":
        return run_id
    result = calculation["result"]
    questions = [f"Please clarify: {result['error']}"] if result["error"] else []
    if result["issues"]:
        questions.extend(
            f"Please clarify {intake_label(g['field'])}: {g['reason']}." for g in result["issues"]
        )
    questions.extend(market_questions)
    questions.append(
        "Confirm obligations held elsewhere and lender eligibility requirements beyond the supplied demo review rules. Passing these checks is not loan approval."
    )
    call(
        "save_draft",
        {
            **stress,
            "calculation_id": result["calculation_id"],
            "statements": [],
            "questions": questions[:30],
        },
    )
    return run_id
