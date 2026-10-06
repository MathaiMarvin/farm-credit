# SPDX-License-Identifier: AGPL-3.0-only
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from farmcredit.interfaces.web.review_views import review_assessment
from farmcredit.interfaces.web.saved_views import (
    assessment_history,
    save_assessment,
    saved_assessment,
)
from farmcredit.interfaces.web.views import workspace

urlpatterns = [
    path("", workspace, name="workspace"),
    path("accounts/login/", LoginView.as_view(template_name="farmcredit/login.html"), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("assessments/<uuid:assessment_id>/review/", review_assessment, name="review-assessment"),
    path("assessments/", assessment_history, name="assessment-history"),
    path("assessments/save/", save_assessment, name="save-assessment"),
    path("assessments/<uuid:assessment_id>/", saved_assessment, name="saved-assessment"),
]
