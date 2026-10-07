# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only, explicitly synthetic introduction to repayment timing."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from farmcredit.adapters.demo import load_demo_case
from farmcredit.application.assess_case import assess_case


@never_cache
@require_GET
def guided_demo(request):
    scenario = request.GET.get("scenario", "baseline")
    error = scenario not in {"baseline", "late", "price"}
    if error:
        scenario = "baseline"
    baseline = load_demo_case()
    sale = baseline.sale
    if scenario == "late":
        sale = replace(sale, received_on=baseline.financing.repayment_on + timedelta(days=14))
    elif scenario == "price":
        sale = replace(sale, price_per_kg=sale.price_per_kg * Decimal("0.90"))
    case = replace(baseline, sale=sale)
    result = assess_case(case)
    context = {
        "scenario": scenario,
        "case": case,
        "result": result,
        "gap": max(Decimal(0), -result.cash_after_repayment),
        "repayment": -case.financing.as_repayment().amount,
        "receipt": sale.as_receipt().amount,
        "difference": result.cash_after_repayment - assess_case(baseline).cash_after_repayment,
        "scenario_error": error,
    }
    template = "farmcredit/demo.html"
    if request.headers.get("HX-Request") == "true":
        template = "farmcredit/demo_scenario.html"
    return render(request, template, context)
