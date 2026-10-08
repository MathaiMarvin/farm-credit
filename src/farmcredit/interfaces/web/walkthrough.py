# SPDX-License-Identifier: AGPL-3.0-only
"""Officer-facing presentation of already recorded results; no financial calculations."""

import re
from decimal import Decimal

from farmcredit.application.intake import intake_label

TOOL_LABELS = {
    "get_case": "Read saved application",
    "get_records": "Inspect source records",
    "assess_cashflow": "Check repayment cash flow",
    "save_draft": "Save draft for officer review",
}
CATEGORY_LABELS = {
    "cash_flow": "Household cash records",
    "harvest": "Harvest assumptions",
    "credit_terms": "Supplied credit terms",
    "repayment_schedule": "Repayment schedule",
    "repayment_history": "Repayment history",
    "yield_history": "Previous yields",
    "savings": "Savings and restrictions",
    "current_obligations": "Existing obligations",
    "lender_policy": "Review policy",
    "market_prices": "WFP market prices",
    "kamis_prices": "KAMIS market prices",
    "weather": "Weather forecast",
}


def application_evidence(brief):
    """Inventory supplied values without treating them as verified evidence."""
    groups = (
        (
            "Household cash",
            "Opening cash, income, expenses and dates covered.",
            ("starts_on", "opening_cash", "coverage_through", "cash/"),
        ),
        ("Harvest and sale", "Harvest, household use, losses, price and payment date.", ("sale.",)),
        (
            "Loan and repayments",
            "Amount borrowed, charges and the dated repayment schedule.",
            ("financing.", "repayment/"),
        ),
    )
    result = []
    for label, purpose, prefixes in groups:
        facts = [fact for fact in brief.facts if fact.field.startswith(prefixes)]
        gaps = [gap for gap in brief.gaps if gap.field.startswith(prefixes)]
        result.append(
            {
                "label": label,
                "purpose": purpose,
                "status": "Needs information" if gaps or not facts else "Supplied · not verified",
                "facts": [
                    {
                        "label": intake_label(fact.field),
                        "value": fact.value,
                        "unit": fact.unit,
                        "basis": ", ".join(
                            sorted(
                                {
                                    record.basis.value
                                    for record in brief.sources
                                    if record.input.field == fact.field
                                }
                            )
                        )
                        or "Not recorded",
                    }
                    for fact in facts
                ],
                "gaps": [{"label": intake_label(gap.field), "reason": gap.reason} for gap in gaps],
            }
        )
    return result


def evidence_readiness(snapshot, baseline, gaps, questions):
    """Explain recorded review checkpoints; never estimate repayment probability."""
    review = (snapshot.get("institution") or {}).get("review", {})
    institution_clear = review.get("status") == "checks_satisfied"
    rows = [
        {
            "label": "Institution checks",
            "clear": institution_clear,
            "status": "Clear in supplied file"
            if institution_clear
            else "Officer review needed"
            if review.get("status") == "officer_review"
            else "Evidence needed",
            "detail": "Repayment history, arrears and obligations are checked against the supplied policy."
            if review
            else "No institutional review is recorded in this finding.",
        },
        {
            "label": "Repayment timing",
            "clear": baseline is not None and not gaps,
            "status": "No dated cash gap"
            if baseline is not None and not gaps
            else "Cash gap found"
            if gaps
            else "Not established",
            "detail": "Compares money available on each date with repayments under the recorded assumptions.",
        },
        {
            "label": "Open evidence questions",
            "clear": not questions,
            "status": f"{len(questions)} to resolve" if questions else "None recorded",
            "detail": "Includes questions from source reviews and the saved finding. Unchecked sources are not verified.",
        },
    ]
    clear = sum(row["clear"] for row in rows)
    return {
        "clear": clear,
        "total": len(rows),
        "rows": rows,
        "label": "Ready for human review" if clear == len(rows) else "Further review needed",
    }


def evidence_progress(calls):
    """Latest recorded category states, including unavailable evidence and failed reads."""
    rows = {}
    for call in calls:
        if call["tool"] != "get_records":
            continue
        for category in call.get("arguments", {}).get("categories", []):
            rows[category] = {
                "label": CATEGORY_LABELS.get(category, category),
                "status": "Checking"
                if call["status"] == "running"
                else "Read failed"
                if call["status"] == "failed"
                else "No result recorded",
            }
        if call["status"] == "succeeded":
            for group in (call.get("result") or {}).get("groups", []):
                category = group["category"]
                rows[category] = {
                    "label": CATEGORY_LABELS.get(category, category),
                    "status": "Available · not verified"
                    if group["status"] == "available"
                    else group["status"].replace("_", " ").capitalize(),
                }
    return list(rows.values())


def activity_rows(calls):
    return [
        {
            "label": TOOL_LABELS.get(call["tool"], call["tool"]),
            "state": call["status"],
            "status": {"running": "In progress", "succeeded": "Recorded", "failed": "Failed"}.get(
                call["status"], call["status"]
            ),
            "detail": ", ".join(
                CATEGORY_LABELS.get(item, item)
                for item in call.get("arguments", {}).get("categories", [])
            ),
            "error": call.get("error"),
            "needs_review": sum(
                group["status"] != "available"
                for group in (call.get("result") or {}).get("groups", [])
            ),
            "findings": [
                {
                    "category": CATEGORY_LABELS.get(group["category"], group["category"]),
                    "status": group["status"],
                    "explanation": group.get("explanation", ""),
                }
                for group in (call.get("result") or {}).get("groups", [])
            ]
            if call["status"] == "succeeded"
            else [],
        }
        for call in calls
    ]


def progress_context(run):
    if not run:
        return {
            "progress_heading": "Starting investigation",
            "progress_message": "Connecting to the investigation service. No checks have started yet.",
            "watch": True,
            "activity": [],
        }
    detail = run.get("event_detail", {})
    if run["status"] == "completed":
        heading, message = (
            "Draft ready for your review",
            "Open the draft to inspect findings, sources and unanswered questions.",
        )
    elif run["status"] == "incomplete":
        heading, message = (
            "Investigation incomplete",
            run.get("reason")
            or "No completed draft was confirmed. Reopen the application to try again.",
        )
    elif run.get("timed_out"):
        heading, message = (
            "Outcome not confirmed",
            "The investigation exceeded its time limit. Open the recorded run before starting another attempt.",
        )
    elif any(call["status"] == "running" for call in run["calls"]):
        current = next(call for call in reversed(run["calls"]) if call["status"] == "running")
        heading = TOOL_LABELS.get(current["tool"], "Checking evidence")
        categories = current.get("arguments", {}).get("categories", [])
        message = (
            f"Checking {len(categories)} evidence categories against this application. "
            "Their recorded status appears below."
            if categories
            else "Waiting for this check to return its recorded result."
        )
    elif run.get("last_event") == "model_failure":
        heading, message = (
            "Model request failed",
            (detail.get("error") or "The model request failed.")
            + (
                f" Retrying once after {detail.get('retry_after', 0.5):g} seconds."
                if detail.get("retry_scheduled")
                else " Recording the final outcome."
            ),
        )
    elif run.get("last_event") == "model_request":
        heading, message = (
            "Waiting for the agent's next action",
            "Waiting for the model response. Completed checks stay visible below; "
            "the next action will appear when it is recorded.",
        )
    else:
        heading, message = (
            "Preparing the next check",
            "The investigation is active. Only recorded actions appear below.",
        )
    return {
        "progress_heading": heading,
        "progress_message": message,
        "watch": run["status"] == "active" and not run.get("timed_out"),
        "activity": activity_rows(run["calls"]),
        "evidence_progress": evidence_progress(run["calls"]),
        "recent_checks": activity_rows(
            [call for call in run["calls"] if call["status"] != "running"][-2:]
        ),
        "completed_checks": sum(call["status"] == "succeeded" for call in run["calls"]),
    }


def review_summary(snapshot):
    calculation = snapshot["calculation"]
    comparison = calculation.get("comparison")
    baseline = comparison["baseline"]["cashflow"] if comparison else None
    gaps = [row for row in baseline["balances"] if Decimal(row["amount"]) < 0] if baseline else []
    if not baseline:
        title = "Evidence needed before a cash-flow finding"
    elif gaps:
        title = "Repayment terms need review"
    else:
        title = "Repayment supported under the recorded assumptions"
    questions = []
    if calculation.get("error"):
        questions.append(calculation["error"])
    questions.extend(
        f"{intake_label(i['field'])}: {i['reason']}" for i in calculation.get("issues", [])
    )
    institution = snapshot.get("institution")
    if institution:
        questions.extend(institution["review"]["questions"])
    for name in ("market", "kamis", "weather"):
        evidence = snapshot.get(name)
        if evidence:
            questions.extend(evidence["review"]["questions"])
    questions.extend(snapshot.get("questions", []))
    scenarios = []
    for scenario in comparison.get("scenarios", []) if comparison else []:
        cashflow = scenario.get("cashflow")
        negative = (
            next((row for row in cashflow["balances"] if Decimal(row["amount"]) < 0), None)
            if cashflow
            else None
        )
        scenarios.append(
            {
                "label": scenario["label"],
                "error": scenario.get("error"),
                "cash_after": cashflow["cash_after_repayment"] if cashflow else None,
                "first_gap": negative,
            }
        )
    questions = list(dict.fromkeys(questions))
    if questions:
        headline = f"{len(questions)} question{'s' if len(questions) != 1 else ''} to resolve"
        next_step = "Review the open questions and evidence before accepting this advisory."
    elif not baseline:
        headline = "More evidence is needed"
        next_step = "Review the evidence request and record what should happen next."
    elif gaps:
        headline = "The repayment plan needs attention"
        next_step = "Review the dated cash gap before accepting this advisory."
    else:
        headline = "Ready for an officer’s review"
        next_step = "Check the sources and assumptions, then record your advisory review."
    return {
        "readiness": evidence_readiness(snapshot, baseline, gaps, questions),
        "headline": headline,
        "next_step": next_step,
        "tone": "attention" if questions or gaps or not baseline else "neutral",
        "title": title,
        "questions": questions,
        "scenarios": scenarios,
        "first_gap": gaps[0] if gaps else None,
        "cash_after": baseline["cash_after_repayment"] if baseline else None,
    }


def advisory_status(context):
    """Describe the recorded review without implying lending authority."""
    review = context["review"]
    if not context["current"] or (review and not context["review_current"]):
        label, tone = "Historical advisory", "muted"
    elif not review:
        label, tone = "Awaiting your review", "attention"
    elif review.decision == "approved":
        label = (
            "Evidence request approved"
            if context["snapshot"]["kind"] == "evidence_request"
            else "Advisory approved"
        )
        tone = "recorded"
    else:
        label, tone = "Changes requested", "attention"
    return {"label": label, "tone": tone, "review": review}


def statement_cards(snapshot):
    """Replace redundant inline record markers with links to the same saved sources."""
    anchors = {
        source["record_id"]: index for index, source in enumerate(snapshot.get("sources", []), 1)
    }
    cards = []
    for statement in snapshot.get("statements", []):
        text = statement["text"]
        citations = []
        for key in statement.get("record_ids", []):
            if key not in anchors:
                continue
            text = re.sub(r"\s*\(record_id:\s*" + re.escape(key) + r"\)", "", text)
            citations.append({"anchor": anchors[key], "record_id": key})
        cards.append({"text": text, "citations": citations})
    return cards


def conversation_turns(application_id, officer_id):
    import json

    from farmcredit.adapters.agent_conversation import conversation_runs, recorded_task
    from farmcredit.adapters.draft_reviews import draft_context

    turns = []
    for run in reversed(list(conversation_runs(application_id, officer_id)[:8])):
        snapshot = json.loads(run.draft.snapshot_json) if run.draft_id else None
        turns.append(
            {
                "run_id": str(run.pk),
                "task": recorded_task(run)
                if run.execution_kind == "model"
                else "Check saved evidence (fixed sequence)",
                "status": run.status,
                "reason": run.reason,
                "draft_id": run.draft_id,
                "advisory_status": advisory_status(draft_context(str(run.draft_id), officer_id))
                if run.draft_id
                else None,
                "summary": review_summary(snapshot) if snapshot else None,
                "statements": statement_cards(snapshot) if snapshot else [],
                "started_at": run.started_at,
            }
        )
    return turns
