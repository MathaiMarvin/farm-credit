# SPDX-License-Identifier: AGPL-3.0-only
"""Presentation-only guidance for incomplete application entry."""

FIELD_HELP = {
    "farmer": "A name or reference you will recognise in your saved applications. Required to save.",
    "farm": "The plot name or identifier, especially if this household farms more than one plot.",
    "location": "Village, ward or county where the crop is grown. Use the most specific location you know.",
    "season": "The growing season and year, for example ‘2027 long rains’.",
    "crop": "Name what the household produces, for example rice, beans rosecoco, potatoes or dairy. Be specific about variety where prices differ.",
    "area_hectares": "The area planted for this application, in hectares. Leave blank if it has not been established.",
    "starts_on": "The first day covered by this cash-flow assessment. Opening cash is the amount available on this day.",
    "opening_cash": "Money available to use on the start date. Exclude restricted savings and the value of supplies bought on credit.",
    "coverage_through": "The last date through which income, expenses and existing debts have been checked. Include the final loan repayment date if the records cover it.",
    "sale_harvest_on": "When the crop is expected to be harvested. This can differ from when the buyer pays.",
    "sale_received_on": "When the household expects to receive the sale money, not just deliver the crop.",
    "sale_gross_kg": "Total expected harvest before subtracting food, seed or losses. Enter kilograms, not bags.",
    "sale_retained_kg": "Kilograms kept for food or seed rather than sold. Enter 0 only if none will be retained.",
    "sale_lost_kg": "Expected kilograms lost before sale, separate from retained food or seed. Leave blank if unknown.",
    "sale_price_per_kg": "The price you expect to receive for one kilogram. This remains an assumption unless supported by a record; market references do not replace it.",
    "financing_supplied_on": "When the supplier will provide the financed inputs, such as seed or fertiliser.",
    "financing_principal": "The cost of inputs supplied on credit, before financing charges. This is not cash paid into the household account.",
    "financing_charges": "Total fees or interest stated in the supplied terms. Enter 0 only if the terms explicitly say there are no charges.",
    "repayment_mode": "Choose one seasonal payment or the instalments stated in the lender’s terms. Enter the actual payments below; no schedule is generated.",
    "schedule_source": "Where the payment terms came from, for example a dated lender offer or repayment agreement.",
    "schedule_version": "The version or date identifying those terms, so changes can be traced.",
    "collection_method": "How payments will be collected, for example mobile money or deductions by the cooperative.",
    "available_records": "List documents you have, information still missing and questions for the agent. Explain any values that have a different source or evidence basis.",
    "recorded_on": "When the source was recorded or the statement was made. This is not a future harvest or repayment date.",
    "basis": "Declared means someone reported it. Assumed means a planning estimate. Observed means it appears in a record. Choose Unknown if you cannot establish the basis.",
}

SECTIONS = (
    (
        "household",
        "1. Household and farm",
        "Start here. A household reference and a named crop or enterprise are enough to begin; you can add missing evidence later.",
        (
            "farmer",
            "cooperative_name",
            "farm",
            "location",
            "season",
            "crop",
            "production_pattern",
            "area_hectares",
        ),
    ),
    (
        "harvest",
        "2. Harvest and sale",
        "Describe what may be sold and when the money arrives. Keep estimates separate from confirmed records.",
        (
            "sale_harvest_on",
            "sale_received_on",
            "sale_gross_kg",
            "sale_retained_kg",
            "sale_lost_kg",
            "sale_price_per_kg",
        ),
    ),
    (
        "financing",
        "3. Financing and repayments",
        "Use the supplied terms. The calculation compares dated payments with the household’s available cash.",
        (
            "financing_supplied_on",
            "financing_principal",
            "financing_charges",
            "repayment_mode",
            "schedule",
            "schedule_source",
            "schedule_version",
            "collection_method",
        ),
    ),
    (
        "cash",
        "4. Household money in and out",
        "Include other income, living costs and existing debts. Leave unknown amounts blank; zero means you know there is none.",
        ("starts_on", "opening_cash", "coverage_through", "cash_records"),
    ),
    (
        "sources",
        "5. Sources and questions",
        "Help the agent distinguish records, statements and assumptions. These source details apply to the values above; describe any exceptions in your notes.",
        ("source", "recorded_on", "basis", "available_records"),
    ),
    (
        "references",
        "6. Records for the agent to check",
        "Optional. Name the relevant market and weather location; the agent checks source coverage when you investigate. Link only an institution file that matches this household. Leaving these blank is better than choosing an unrelated file.",
        (
            "institution_record_set",
            "market_reference",
            "kamis_county",
            "kamis_classification",
            "kamis_market_reference",
            "weather_reference",
        ),
    ),
)


def form_sections(form):
    return [
        {
            "key": key,
            "title": title,
            "description": description,
            "fields": [form[name] for name in names],
            "open": key == "household" or any(form[name].errors for name in names),
        }
        for key, title, description, names in SECTIONS
    ]
