# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence records. Financial rules live in the domain package."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CaseState(models.Model):
    case_id = models.CharField(max_length=100, primary_key=True)
    fingerprint = models.CharField(max_length=64, null=True)
    revision = models.PositiveIntegerField(default=0)


class Assessment(models.Model):
    assessment_id = models.CharField(max_length=64, primary_key=True)
    case = models.ForeignKey(CaseState, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    saved_at = models.DateTimeField(default=timezone.now)
    snapshot_json = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["case", "version"], name="assessment_case_version"),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="assessment_positive_version"
            ),
        ]
        ordering = ["-version"]


class Review(models.Model):
    operation_id = models.CharField(max_length=64, primary_key=True)
    assessment = models.OneToOneField(Assessment, on_delete=models.PROTECT)
    case_revision = models.PositiveIntegerField()
    decision = models.CharField(max_length=20)
    note = models.CharField(max_length=2000)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    officer_name = models.CharField(max_length=301)
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(decision__in=["approved", "changes_requested"]),
                name="review_valid_decision",
            )
        ]


class Draft(models.Model):
    operation_id = models.CharField(max_length=64, primary_key=True)
    assessment = models.ForeignKey(Assessment, on_delete=models.PROTECT)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    case_revision = models.PositiveIntegerField()
    version = models.PositiveIntegerField()
    request_json = models.TextField()
    snapshot_json = models.TextField()
    saved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "version"], name="draft_assessment_version"
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="draft_positive_version"
            ),
        ]
