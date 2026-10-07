# SPDX-License-Identifier: AGPL-3.0-only
"""Inspect saved drafts and record an authenticated human decision."""

from decimal import Decimal
from uuid import uuid4

from django.core import signing
from django.db import DatabaseError
from django.http import Http404, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from farmcredit.adapters.draft_reviews import draft_context, review_draft
from farmcredit.adapters.persistence.models import ApplicationVersion
from farmcredit.application.intake import intake_label
from farmcredit.domain.draft_review import DraftReviewRequest
from farmcredit.domain.review import Officer
from farmcredit.interfaces.web.walkthrough import advisory_status, review_summary


def _render_draft(request, draft_id, *, error=None, status=200, note=""):
    try:
        context = draft_context(str(draft_id), str(request.user.pk))
    except PermissionError:
        return HttpResponseForbidden("A named account with advisory-review permission is required.")
    except LookupError as exception:
        raise Http404("Draft not found.") from exception
    except DatabaseError:
        return render(
            request,
            "farmcredit/draft.html",
            {"storage_error": "Draft storage is temporarily unavailable. Try reopening this page."},
            status=503,
        )
    snapshot = context["snapshot"]
    comparison = snapshot["calculation"]["comparison"]
    baseline = comparison["baseline"]["cashflow"] if comparison else None
    shortfalls = (
        [row for row in baseline["balances"] if Decimal(row["amount"]) < 0] if baseline else []
    )
    anchors = {source["record_id"]: index for index, source in enumerate(snapshot["sources"], 1)}
    context.update(
        {
            "baseline": baseline,
            "summary": review_summary(snapshot),
            "advisory_status": advisory_status(context),
            "latest_application": ApplicationVersion.objects.filter(
                case_id=context["draft"].application.case_id, officer=request.user
            ).first()
            if context["draft"].application_id
            else None,
            "calculation_issues": [
                {"label": intake_label(issue["field"]), "reason": issue["reason"]}
                for issue in snapshot["calculation"]["issues"]
            ],
            "shortfalls": shortfalls,
            "statements": [
                {
                    "text": item["text"],
                    "citations": [
                        {"record_id": key, "anchor": anchors[key]} for key in item["record_ids"]
                    ],
                }
                for item in snapshot["statements"]
            ],
            "error": error,
            "note": note,
        }
    )
    if context["current"] and not context["review"]:
        context["review_token"] = signing.dumps(
            {
                "draft_id": str(draft_id),
                "officer_id": str(request.user.pk),
                "revision": context["revision"],
                "operation_id": str(uuid4()),
            },
            salt="draft-review",
        )
    return render(request, "farmcredit/draft.html", context, status=status)


@never_cache
@require_GET
def saved_draft(request, draft_id):
    return _render_draft(request, draft_id)


@never_cache
@require_POST
def submit_draft_review(request, draft_id):
    note = request.POST.get("note", "").strip()
    try:
        token = signing.loads(
            request.POST.get("review_token", ""), salt="draft-review", max_age=1800
        )
        if token["draft_id"] != str(draft_id) or token["officer_id"] != str(request.user.pk):
            raise signing.BadSignature("Wrong draft or officer.")
    except (signing.BadSignature, KeyError, TypeError):
        return _render_draft(
            request,
            draft_id,
            error="This review form expired or changed. Check the draft and submit the refreshed form.",
            status=400,
            note=note,
        )
    try:
        review_draft(
            DraftReviewRequest(
                str(draft_id),
                token["operation_id"],
                token["revision"],
                request.POST.get("decision", ""),
                note,
                Officer(str(request.user.pk), request.user.get_full_name().strip(), False),
            )
        )
    except PermissionError:
        return HttpResponseForbidden("A named account with advisory-review permission is required.")
    except LookupError as exception:
        raise Http404("Draft not found.") from exception
    except ValueError as exception:
        return _render_draft(request, draft_id, error=str(exception), status=409, note=note)
    except DatabaseError:
        return _render_draft(
            request,
            draft_id,
            error="Saving the review could not be confirmed. Check the status below before retrying.",
            status=503,
            note=note,
        )
    return redirect("saved-draft", draft_id=draft_id)
