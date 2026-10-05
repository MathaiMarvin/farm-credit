# SPDX-License-Identifier: AGPL-3.0-only
from django.urls import path

from farmcredit.interfaces.web.views import workspace

urlpatterns = [path("", workspace, name="workspace")]
