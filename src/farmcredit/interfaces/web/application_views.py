# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated intake and the fixed evidence check over a saved version."""

import json
from uuid import uuid4

from django.core import signing
from django.db import DatabaseError
from django.http import Http404, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from farmcredit.adapters.agent_runs import run_details
from farmcredit.adapters.application_store import get_application, save_application
from farmcredit.adapters.case_reader import _require_officer, bind_application_reader
from farmcredit.adapters.institution_demo import MEMBER_CHOICES, demo_application_data
from farmcredit.adapters.intake_investigation import investigate_application
from farmcredit.adapters.persistence.models import AgentRun, ApplicationVersion, Draft
from farmcredit.application.intake import intake_label
from farmcredit.interfaces.mcp.investigation import investigate_application_with_model
from farmcredit.interfaces.web.forms import ApplicationForm


def _failure(request, error):
    if isinstance(error, PermissionError):
        return HttpResponseForbidden("A named officer with advisory-review permission is required.")
    if isinstance(error, LookupError):
        raise Http404("Application or run not found.") from error
    return render(
        request,
        "farmcredit/application_error.html",
        {"error": "Storage is temporarily unavailable. Reopen the application before retrying."},
        status=503,
    )


@never_cache
@require_GET
def applications(request):
    try:
        _require_officer(str(request.user.pk))
        rows = (
            ApplicationVersion.objects.filter(officer=request.user)
            .order_by("case_id", "-version")
            .distinct("case_id")
        )
        return render(
            request,
            "farmcredit/applications.html",
            {
                "demo_households": MEMBER_CHOICES,
                "applications": [
                    {
                        "id": row.pk,
                        "version": row.version,
                        "saved_at": row.saved_at,
                        "farmer": json.loads(row.snapshot_json)["inputs"]["context"]["farmer"],
                    }
                    for row in rows
                ],
            },
        )
    except (PermissionError, DatabaseError) as error:
        return _failure(request, error)


@never_cache
@require_http_methods(["GET", "POST"])
def application_intake(request, application_id=None):
    officer_id = str(request.user.pk)
    try:
        _require_officer(officer_id)
        saved = get_application(str(application_id), officer_id) if application_id else None
        initial = saved.snapshot["inputs"]["intake"] if saved else {}
        if not saved and request.method == "GET" and request.GET.get("demo"):
            try:
                initial = demo_application_data(request.GET["demo"])
                initial["market_reference"] = "Nakuru"
                initial["kamis_market_reference"] = "Nakuru Wakulima"
                initial["weather_reference"] = "Nakuru"
            except ValueError:
                return HttpResponseBadRequest("Unknown synthetic household.")
        form = ApplicationForm(request.POST if request.method == "POST" else None, initial=initial)
        token = (
            request.POST.get("save_token", "")
            if request.method == "POST"
            else signing.dumps(
                {
                    "officer_id": officer_id,
                    "previous_id": saved.application_id if saved else None,
                    "operation_id": str(uuid4()),
                },
                salt="application-save",
            )
        )
        status = 200
        if request.method == "POST":
            try:
                binding = signing.loads(token, salt="application-save", max_age=7200)
                if binding["officer_id"] != officer_id or binding["previous_id"] != (
                    saved.application_id if saved else None
                ):
                    raise signing.BadSignature
            except (signing.BadSignature, KeyError, TypeError):
                form.is_valid()
                form.add_error(
                    None, "This save form expired or changed. Reopen the application before saving."
                )
                status = 400
            else:
                if form.is_valid():
                    try:
                        result = save_application(
                            officer_id=officer_id,
                            inputs=form.inputs,
                            operation_id=binding["operation_id"],
                            previous_id=binding["previous_id"],
                        )
                    except ValueError as error:
                        form.add_error(None, str(error))
                        status = 409
                    else:
                        return redirect("application-intake", application_id=result.application_id)
                else:
                    status = 400
        context = {"form": form, "saved": saved, "save_token": token}
        if saved:
            context.update(
                brief=bind_application_reader(
                    officer_id=officer_id, application_id=saved.application_id
                ).get_case(),
                versions=ApplicationVersion.objects.filter(
                    case_id=saved.case_id, officer=request.user
                ),
                drafts=Draft.objects.filter(application_id=saved.application_id).order_by(
                    "-version"
                ),
                runs=AgentRun.objects.filter(
                    application_id=saved.application_id, officer=request.user
                ).order_by("-started_at"),
            )
            context["gaps"] = [
                {"label": intake_label(gap.field), "reason": gap.reason}
                for gap in context["brief"].gaps
            ]
        return render(request, "farmcredit/application.html", context, status=status)
    except (PermissionError, LookupError, DatabaseError) as error:
        return _failure(request, error)


@never_cache
@require_POST
def investigate(request, application_id):
    try:
        mode = request.POST.get("mode", "fixed")
        if mode not in {"fixed", "model"}:
            return HttpResponseBadRequest("Unknown investigation mode.")
        investigate_case = (
            investigate_application_with_model if mode == "model" else investigate_application
        )
        run_id = investigate_case(
            application_id=str(application_id), officer_id=str(request.user.pk)
        )
    except (PermissionError, LookupError, DatabaseError) as error:
        return _failure(request, error)
    except ValueError as error:
        return render(
            request, "farmcredit/application_error.html", {"error": str(error)}, status=409
        )
    return redirect("application-run", run_id=run_id)


@never_cache
@require_GET
def application_run(request, run_id):
    try:
        details = run_details(run_id=str(run_id), officer_id=str(request.user.pk))
        return render(request, "farmcredit/application_run.html", {"run": details})
    except (PermissionError, LookupError, DatabaseError) as error:
        return _failure(request, error)
