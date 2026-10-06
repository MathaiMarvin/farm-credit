# SPDX-License-Identifier: AGPL-3.0-only
"""Local demo configuration; not a production deployment configuration."""

import os
import secrets
from pathlib import Path

SECRET_KEY = os.environ.get("FARMCREDIT_SECRET_KEY") or secrets.token_urlsafe(50)
DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]
ROOT_URLCONF = "farmcredit.interfaces.web.urls"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.staticfiles",
    "farmcredit.interfaces.web",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.csrf",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
            ]
        },
    }
]
STATIC_URL = "/static/"
TIME_ZONE = "Africa/Nairobi"
USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ASSESSMENT_DB = Path(os.environ.get("FARMCREDIT_ASSESSMENT_DB", ".local/assessments.sqlite3"))


AUTH_DB = Path(os.environ.get("FARMCREDIT_AUTH_DB", ".local/auth.sqlite3"))
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": AUTH_DB}}
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/assessments/"
LOGOUT_REDIRECT_URL = "/"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
