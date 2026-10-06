# SPDX-License-Identifier: AGPL-3.0-only
"""Require a session for application views, including partial requests."""

from django.contrib.auth.middleware import LoginRequiredMiddleware
from django.contrib.auth.views import redirect_to_login
from django.urls import reverse
from django.utils.cache import add_never_cache_headers


class WorkspaceLoginRequiredMiddleware(LoginRequiredMiddleware):
    def handle_no_permission(self, request, view_func):
        response = super().handle_no_permission(request, view_func)
        if request.method not in {"GET", "HEAD"} and request.path != reverse("workspace"):
            target = reverse("workspace")
            match = request.resolver_match
            if match and match.url_name == "review-assessment":
                target = reverse(
                    "saved-assessment", kwargs={"assessment_id": match.kwargs["assessment_id"]}
                )
            # Signing in must return to a readable page, never a POST-only endpoint.
            response = redirect_to_login(target, self.get_login_url(view_func))
        add_never_cache_headers(response)
        if request.headers.get("HX-Request") == "true":
            # Navigate the whole browser instead of inserting sign-in into a result panel.
            response["HX-Redirect"] = response["Location"]
            del response["Location"]
            response.status_code = 401
        return response
