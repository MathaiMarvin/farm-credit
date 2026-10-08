# SPDX-License-Identifier: AGPL-3.0-only
from uuid import uuid4

import test_applications as fixtures
from django.test import TransactionTestCase, override_settings

from farmcredit.adapters.persistence.models import AgentRun, ApplicationVersion
from farmcredit.interfaces.web.forms import ApplicationForm
from farmcredit.interfaces.web.intake_guidance import form_sections


@override_settings(ALLOWED_HOSTS=["testserver"])
class GuidedIntakeTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp

    def test_every_field_has_guidance_and_appears_in_one_section(self):
        form = ApplicationForm()
        names = [field.name for section in form_sections(form) for field in section["fields"]]
        self.assertCountEqual(names, form.fields)
        self.assertTrue(all(field.help_text for field in form.fields.values()))

    def test_incomplete_save_return_and_resume_preserve_unknowns(self):
        page = self.client.get("/applications/new/")
        response = self.client.post(
            "/applications/new/",
            {
                **fixtures.intake_data(),
                "save_token": page.context["save_token"],
                "save_action": "later",
            },
            follow=True,
        )
        self.assertContains(response, "Application saved.")
        self.assertContains(response, "Continue editing")
        saved = ApplicationVersion.objects.get()
        reopened = self.client.get(f"/applications/{saved.pk}/")
        self.assertIsNone(reopened.context["form"].initial["opening_cash"])
        self.assertTrue(reopened.context["form"].initial["farmer"])
        self.assertEqual(AgentRun.objects.count(), 0)
        self.assertNotContains(
            self.client.get(f"/applications/?saved={uuid4()}"), "Application saved."
        )

    def test_save_handoff_replaces_editor_fragment(self):
        page = self.client.get("/applications/new/")
        response = self.client.post(
            "/applications/new/",
            {**fixtures.intake_data(), "save_token": page.context["save_token"]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith("/#agent-heading"))
        self.assertEqual(AgentRun.objects.count(), 0)

    def test_errors_open_the_affected_section_and_keep_values(self):
        page = self.client.get("/applications/new/")
        response = self.client.post(
            "/applications/new/",
            {
                **fixtures.intake_data(),
                "save_token": page.context["save_token"],
                "sale_gross_kg": "-4",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'href="#id_sale_gross_kg"', status_code=400)
        section = next(s for s in response.context["form_sections"] if s["key"] == "harvest")
        self.assertTrue(section["open"])
        self.assertEqual(response.context["form"]["farmer"].value(), "Synthetic household A")
        self.assertEqual(ApplicationVersion.objects.count(), 0)

    def test_named_enterprise_and_location_are_saved_without_demo_substitution(self):
        page = self.client.get("/applications/new/")
        response = self.client.post(
            "/applications/new/",
            {
                **fixtures.intake_data(),
                "save_token": page.context["save_token"],
                "crop": "rice",
                "production_pattern": "single_harvest",
                "cooperative_name": "Lake growers",
                "location": "Ahero",
                "kamis_county": "Kisumu",
                "kamis_market_reference": "Ahero",
                "weather_reference": "Kisumu",
                "market_reference": "Kisumu",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        context = response.context["brief"].context
        self.assertEqual(context["crop"], "rice")
        self.assertEqual(context["institution"], "Lake growers")
        from farmcredit.adapters.case_reader import bind_application_reader

        reader = bind_application_reader(
            officer_id=self.officer_id, application_id=str(ApplicationVersion.objects.get().pk)
        )
        self.assertIsNone(reader.get_institution())
        self.assertIsNone(reader.get_records(("lender_policy",)).institution_policy)
        self.assertEqual(context["weather_reference"], "Kisumu")
        self.assertFalse(
            any(
                gap.field in {"crop", "production_pattern"}
                for gap in response.context["brief"].gaps
            )
        )

    def test_recurring_enterprise_can_be_saved_but_not_forced_into_harvest_model(self):
        form = ApplicationForm(
            {
                **fixtures.intake_data(complete=True),
                "crop": "dairy",
                "production_pattern": "recurring",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        saved = fixtures.ApplicationTests.save(
            self,
            {
                **fixtures.intake_data(complete=True),
                "crop": "dairy",
                "production_pattern": "recurring",
            },
        )
        response = self.client.get(f"/applications/{saved.application_id}/")
        self.assertTrue(
            any(gap.field == "production_pattern" for gap in response.context["brief"].gaps)
        )
