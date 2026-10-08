# SPDX-License-Identifier: AGPL-3.0-only
"""A single application journey; old shared assessment URLs expose no records."""

from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache


@never_cache
def application_home(request):
    if request.method in {"GET", "HEAD"}:
        return redirect("applications")
    return retired_assessment(request)


@never_cache
def retired_assessment(request, assessment_id=None):
    return render(request, "farmcredit/retired_assessment.html", status=410)
