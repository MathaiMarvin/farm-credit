# SPDX-License-Identifier: AGPL-3.0-only
from dataclasses import replace

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from farmcredit.adapters.demo import load_demo_case
from farmcredit.application.assess_case import assess_case
from farmcredit.interfaces.web.forms import ScenarioForm


@never_cache
@require_http_methods(["GET", "POST"])
def workspace(request):
    case = load_demo_case()
    form = ScenarioForm(
        request.POST if request.method == "POST" else None,
        initial={
            "received_on": case.sale.received_on,
            "price_per_kg": case.sale.price_per_kg,
        },
    )
    result = None
    if request.method == "POST" and form.is_valid():
        case = replace(case, sale=replace(case.sale, **form.cleaned_data))
        try:
            result = assess_case(case)
        except ValueError as error:
            form.add_error(None, str(error))
    context = {
        "case": case,
        "form": form,
        "result": result,
        "cash_records": sorted(case.other_movements, key=lambda movement: movement.on),
        "repayment_amount": -case.financing.as_repayment().amount,
        "shortfall_amount": -result.cash_after_repayment
        if result and result.cash_after_repayment < 0
        else None,
    }
    template = "farmcredit/workspace.html"
    if request.headers.get("HX-Request") == "true":
        template = "farmcredit/calculation.html"
    return render(request, template, context)
