# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated review endpoint; identity always comes from the session."""

import sqlite3

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.domain.review import Officer, ReviewRequest


def is_reviewer(user) -> bool:
    return (
        user.is_authenticated
        and user.is_active
        and user.has_perm("auth.review_assessment")
        and bool(user.get_full_name().strip())
    )


@never_cache
@login_required
@require_POST
def review_assessment(request, assessment_id):
    if not is_reviewer(request.user):
        return HttpResponseForbidden("A named account with advisory-review permission is required.")
    try:
        token = signing.loads(
            request.POST.get("review_token", ""), salt="advisory-review", max_age=1800
        )
        if token["assessment_id"] != str(assessment_id) or token["officer_id"] != str(
            request.user.pk
        ):
            return HttpResponseBadRequest(
                "This review form belongs to another assessment or officer."
            )
    except signing.BadSignature:
        return HttpResponseBadRequest(
            "Review form expired or changed. Reopen the saved assessment."
        )
    review = ReviewRequest(
        str(assessment_id),
        token["operation_id"],
        token["revision"],
        request.POST.get("decision", ""),
        request.POST.get("note", "").strip(),
        Officer(str(request.user.pk), request.user.get_full_name().strip(), True),
    )
    try:
        AssessmentStore(settings.ASSESSMENT_DB).review(review)
    except ValueError as error:
        return render(
            request,
            "farmcredit/review_error.html",
            {"error": str(error), "assessment_id": assessment_id},
            status=409,
        )
    except (OSError, sqlite3.Error):
        return render(
            request,
            "farmcredit/review_error.html",
            {
                "error": "Review storage is unavailable. Reopen the assessment to check its status before retrying.",
                "assessment_id": assessment_id,
            },
            status=503,
        )
    return redirect("saved-assessment", assessment_id=assessment_id)
