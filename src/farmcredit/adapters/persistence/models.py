# SPDX-License-Identifier: AGPL-3.0-only
"""Persistence records. Financial rules live in the domain package."""

from django.conf import settings
from django.db import models
from django.utils import timezone


class CaseState(models.Model):
    case_id = models.CharField(max_length=100, primary_key=True)
    fingerprint = models.CharField(max_length=64, null=True)
    revision = models.PositiveIntegerField(default=0)


class ApplicationVersion(models.Model):
    application_id = models.UUIDField(primary_key=True)
    case = models.ForeignKey(CaseState, on_delete=models.PROTECT)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    version = models.PositiveIntegerField()
    saved_at = models.DateTimeField(default=timezone.now)
    snapshot_json = models.TextField()

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["case", "version"], name="application_case_version"),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="application_positive_version"
            ),
        ]


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
    assessment = models.ForeignKey(Assessment, null=True, on_delete=models.PROTECT)
    application = models.ForeignKey(ApplicationVersion, null=True, on_delete=models.PROTECT)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    case_revision = models.PositiveIntegerField()
    version = models.PositiveIntegerField()
    request_json = models.TextField()
    snapshot_json = models.TextField()
    saved_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["application", "version"], name="draft_application_version"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(assessment__isnull=False, application__isnull=True)
                    | models.Q(assessment__isnull=True, application__isnull=False)
                ),
                name="draft_one_input_binding",
            ),
            models.UniqueConstraint(
                fields=["assessment", "version"], name="draft_assessment_version"
            ),
            models.CheckConstraint(
                condition=models.Q(version__gt=0), name="draft_positive_version"
            ),
        ]


class DraftReview(models.Model):
    operation_id = models.CharField(max_length=64, primary_key=True)
    draft = models.OneToOneField(Draft, on_delete=models.PROTECT, related_name="review")
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
                name="draft_review_valid_decision",
            ),
        ]


class AgentRun(models.Model):
    execution_kind = models.CharField(max_length=24, default="internal_tools")
    model = models.CharField(max_length=200, blank=True)
    run_id = models.UUIDField(primary_key=True)
    assessment = models.ForeignKey(Assessment, null=True, on_delete=models.PROTECT)
    application = models.ForeignKey(ApplicationVersion, null=True, on_delete=models.PROTECT)
    officer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    scope_json = models.TextField()
    case_revision = models.PositiveIntegerField()
    status = models.CharField(max_length=20, default="active")
    reason = models.CharField(max_length=256, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)
    draft = models.OneToOneField(Draft, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(assessment__isnull=False, application__isnull=True)
                    | models.Q(assessment__isnull=True, application__isnull=False)
                ),
                name="agentrun_one_input_binding",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["active", "completed", "incomplete"]),
                name="run_valid_status",
            ),
        ]


class ToolCall(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.PROTECT, related_name="calls")
    operation_id = models.UUIDField()
    sequence = models.PositiveIntegerField()
    tool = models.CharField(max_length=40)
    arguments_json = models.TextField()
    status = models.CharField(max_length=20, default="running")
    result_json = models.TextField(null=True)
    error = models.CharField(max_length=256, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "operation_id"], name="run_call_operation"),
            models.UniqueConstraint(fields=["run", "sequence"], name="run_call_sequence"),
            models.CheckConstraint(
                condition=models.Q(status__in=["running", "succeeded", "failed"]),
                name="call_valid_status",
            ),
        ]
        ordering = ["sequence"]


class InvestigationEvent(models.Model):
    """Append-only requests and outcomes; a request without an outcome is unknown."""

    run = models.ForeignKey(AgentRun, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=40)
    payload_json = models.TextField()
    recorded_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["pk"]


class RunEvidence(models.Model):
    run = models.ForeignKey(AgentRun, on_delete=models.PROTECT, related_name="evidence")
    category = models.CharField(max_length=40)
    snapshot_json = models.TextField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["run", "category"], name="run_evidence_category"),
        ]
