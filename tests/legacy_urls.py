"""Test-only routes for retained historical calculator code; never deployed."""

# SPDX-License-Identifier: AGPL-3.0-only
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from farmcredit.interfaces.web import application_views
from farmcredit.interfaces.web.demo_views import guided_demo
from farmcredit.interfaces.web.draft_views import saved_draft, submit_draft_review
from farmcredit.interfaces.web.review_views import review_assessment
from farmcredit.interfaces.web.saved_views import (
    assessment_history,
    save_assessment,
    saved_assessment,
)
from farmcredit.interfaces.web.views import workspace

urlpatterns = [
    path("demo/", guided_demo, name="guided-demo"),
    path("applications/", application_views.applications, name="applications"),
    path("applications/new/", application_views.application_intake, name="application-new"),
    path(
        "applications/<uuid:application_id>/",
        application_views.application_intake,
        name="application-intake",
    ),
    path(
        "applications/<uuid:application_id>/investigate/",
        application_views.investigate,
        name="application-investigate",
    ),
    path(
        "runs/<uuid:run_id>/progress/",
        application_views.investigation_progress,
        name="investigation-progress",
    ),
    path("runs/<uuid:run_id>/", application_views.application_run, name="application-run"),
    path("", workspace, name="workspace"),
    path(
        "accounts/login/",
        LoginView.as_view(template_name="farmcredit/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("assessments/<uuid:assessment_id>/review/", review_assessment, name="review-assessment"),
    path("drafts/<str:draft_id>/review/", submit_draft_review, name="review-draft"),
    path("drafts/<str:draft_id>/", saved_draft, name="saved-draft"),
    path("assessments/", assessment_history, name="assessment-history"),
    path("assessments/save/", save_assessment, name="save-assessment"),
    path("assessments/<uuid:assessment_id>/", saved_assessment, name="saved-assessment"),
]
