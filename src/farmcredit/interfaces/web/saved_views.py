# SPDX-License-Identifier: AGPL-3.0-only
"""Read immutable snapshots and accept server-signed calculation saves."""

import logging
import sqlite3

from django.conf import settings
from django.core import signing
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.application.saved_assessments import SCHEMA_VERSION

logger = logging.getLogger(__name__)


@never_cache
@require_http_methods(["POST"])
def save_assessment(request):
    token = request.POST.get("calculation", "")
    try:
        calculation = signing.loads(token, salt="assessment-save", max_age=1800)
    except signing.BadSignature:
        return HttpResponseBadRequest(
            "Calculation expired or changed. Calculate again before saving."
        )
    try:
        saved = AssessmentStore(settings.ASSESSMENT_DB).save(
            calculation["snapshot_json"],
            calculation["operation_id"],
        )
    except (OSError, sqlite3.Error):
        logger.exception("Assessment save failed")
        return render(
            request,
            "farmcredit/saved_assessments.html",
            {
                "storage_error": "Saving failed. Your calculation has not been confirmed saved. Retry below.",
                "save_token": token,
            },
            status=503,
        )
    except ValueError:
        return HttpResponseBadRequest("Save conflict. Calculate again to create a new version.")
    return redirect("saved-assessment", assessment_id=saved.assessment_id)


@never_cache
@require_http_methods(["GET"])
def assessment_history(request):
    try:
        history = AssessmentStore(settings.ASSESSMENT_DB).history("FC-001")
    except (OSError, sqlite3.Error):
        logger.exception("Assessment history unavailable")
        return render(
            request,
            "farmcredit/saved_assessments.html",
            {"storage_error": "Saved assessments are temporarily unavailable."},
            status=503,
        )
    return render(request, "farmcredit/saved_assessments.html", {"history": history})


@never_cache
@require_http_methods(["GET"])
def saved_assessment(request, assessment_id):
    try:
        saved = AssessmentStore(settings.ASSESSMENT_DB).get(str(assessment_id))
    except (OSError, sqlite3.Error):
        logger.exception("Saved assessment unavailable")
        return render(
            request,
            "farmcredit/saved_assessments.html",
            {"storage_error": "This saved assessment is temporarily unavailable."},
            status=503,
        )
    if saved is None:
        raise Http404("Saved assessment not found.")
    snapshot = saved.snapshot
    if snapshot["schema_version"] != SCHEMA_VERSION:
        return HttpResponseBadRequest(
            "This snapshot format requires a compatible application version."
        )
    return render(
        request, "farmcredit/saved_assessments.html", {"saved": saved, "snapshot": snapshot}
    )
