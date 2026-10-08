# SPDX-License-Identifier: AGPL-3.0-only
"""Published routes keep the officer journey separate from archived shared data."""

from unittest.mock import patch
from uuid import uuid4

import test_applications as fixtures
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings


@override_settings(ALLOWED_HOSTS=["testserver"])
class CleanJourneyTests(TransactionTestCase):
    setUp = fixtures.ApplicationTests.setUp
    save = fixtures.ApplicationTests.save

    def test_home_and_old_list_lead_to_own_applications(self):
        saved = self.save()
        joy = get_user_model().objects.create_user("joy", first_name="Joy")
        joy.user_permissions.set(self.officer.user_permissions.all())
        self.client.force_login(joy)
        for url in ("/", "/assessments/"):
            response = self.client.get(url, follow=True)
            self.assertRedirects(response, "/applications/")
            self.assertContains(response, "No saved applications yet.")
            self.assertNotContains(response, saved.application_id)
            self.assertNotContains(response, ">Household case</a>")
            self.assertNotContains(response, ">Saved assessments</a>")
        self.assertEqual(self.client.get(f"/applications/{saved.application_id}/").status_code, 404)

    def test_retired_routes_never_read_or_write_assessments(self):
        assessment_id = uuid4()
        with patch("farmcredit.interfaces.web.saved_views.AssessmentStore") as store:
            for url in (
                "/assessments/save/",
                f"/assessments/{assessment_id}/",
                f"/assessments/{assessment_id}/review/",
            ):
                for method in (self.client.get, self.client.post):
                    with self.subTest(url=url, method=method.__name__):
                        response = method(url)
                        self.assertContains(response, "Continue in Applications", status_code=410)
                        self.assertIn("no-store", response["Cache-Control"])
            for url in ("/", "/assessments/"):
                self.assertEqual(self.client.post(url).status_code, 410)
            store.assert_not_called()
