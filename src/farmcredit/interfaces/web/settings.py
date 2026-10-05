# SPDX-License-Identifier: AGPL-3.0-only
"""Local demo configuration; not a production deployment configuration."""

import os
import secrets

SECRET_KEY = os.environ.get("FARMCREDIT_SECRET_KEY") or secrets.token_urlsafe(50)
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
ROOT_URLCONF = "farmcredit.interfaces.web.urls"
INSTALLED_APPS = ["django.contrib.staticfiles", "farmcredit.interfaces.web"]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.csrf"]},
    }
]
STATIC_URL = "/static/"
TIME_ZONE = "Africa/Nairobi"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
