# SPDX-License-Identifier: AGPL-3.0-only
from copy import deepcopy
from pathlib import Path

from django.template import Context, Template
from django.test import SimpleTestCase

from farmcredit.interfaces.web.forms import ApplicationForm
from farmcredit.interfaces.web.presentation import display_data, display_text


class PresentationTests(SimpleTestCase):
    def test_source_and_agent_text_keep_qualifications_and_escape_html(self):
        result = Template("{% load presentation %}{{ text|ui_text }}").render(
            Context(
                {"text": "Synthetic records are assumed, not verified. <script>alert(1)</script>"}
            )
        )
        self.assertIn("Supplied records are assumed, not verified.", result)
        self.assertNotIn("<script>", result)
        self.assertNotIn("synthetic", result.lower())
        self.assertEqual(
            display_text("Fictional household; fictitious file"),
            "Supplied household; supplied file",
        )

    def test_trace_presentation_does_not_change_original(self):
        trace = {"synthetic": True, "records": [{"source": "Synthetic worksheet", "amount": "0"}]}
        original = deepcopy(trace)
        shown = display_data(trace)
        self.assertEqual(trace, original)
        self.assertNotIn("synthetic", str(shown).lower())
        self.assertEqual(shown["records"][0]["amount"], "0")

    def test_saved_text_round_trips_without_rewriting_original(self):
        initial = {"source": "Synthetic worksheet", "farmer": "Synthetic household"}
        original = initial.copy()
        form = ApplicationForm(initial=initial)
        self.assertNotIn("Synthetic", str(form["source"]))
        self.assertEqual(initial, original)
        posted = ApplicationForm(
            data={"source": "Supplied worksheet", "farmer": "Supplied household"},
            initial=initial,
        )
        posted.is_valid()
        self.assertEqual(posted.cleaned_data["source"], original["source"])
        self.assertEqual(initial, original)

    def test_explicit_source_edit_is_preserved(self):
        form = ApplicationForm(
            data={"source": "Officer worksheet"}, initial={"source": "Synthetic worksheet"}
        )
        form.is_valid()
        self.assertEqual(form.cleaned_data["source"], "Officer worksheet")

    def test_templates_have_no_origin_disclosure_copy(self):
        root = Path(__file__).parents[1] / "src/farmcredit/interfaces/web/templates/farmcredit"
        import re

        for path in root.glob("*.html"):
            text = re.sub(r"{%.*?%}|{{.*?}}", "", path.read_text(), flags=re.DOTALL)
            with self.subTest(template=path.name):
                self.assertNotRegex(text.lower(), r"\b(synthetic|fictional|fictitious)\b")
