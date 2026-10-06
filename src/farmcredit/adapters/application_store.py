# SPDX-License-Identifier: AGPL-3.0-only
"""Officer-owned synthetic applications with append-only versions."""

from uuid import UUID

from django.db import transaction

from farmcredit.adapters.persistence.models import ApplicationVersion, CaseState
from farmcredit.application.intake import SavedApplication
from farmcredit.application.saved_assessments import (
    SCHEMA_VERSION,
    canonical_json,
    input_fingerprint,
)


def _saved(row):
    return SavedApplication(
        str(row.pk), row.case_id, row.version, row.saved_at.isoformat(), row.snapshot_json
    )


def get_application(application_id: str, officer_id: str) -> SavedApplication:
    from farmcredit.adapters.case_reader import _require_officer

    _require_officer(officer_id)
    try:
        key = UUID(str(application_id))
    except ValueError:
        raise LookupError("Application not found.") from None
    row = ApplicationVersion.objects.filter(pk=key, officer_id=officer_id).first()
    if row is None:
        raise LookupError("Application not found.")
    return _saved(row)


@transaction.atomic
def save_application(
    *, officer_id: str, inputs: dict, operation_id: str, previous_id: str | None = None
) -> SavedApplication:
    from django.utils import timezone

    from farmcredit.adapters.case_reader import _require_officer
    from farmcredit.application.get_case import CaseScope, get_case

    _require_officer(officer_id)
    previous = get_application(previous_id, officer_id) if previous_id else None
    # A retry locks the same case as its first save, including first-version saves.
    case_id = previous.case_id if previous else f"APP-{UUID(operation_id)}"
    CaseState.objects.get_or_create(case_id=case_id)
    state = CaseState.objects.select_for_update().get(pk=case_id)
    fingerprint = input_fingerprint(inputs)
    snapshot = canonical_json(
        {
            "schema_version": SCHEMA_VERSION,
            "case_id": case_id,
            "inputs": inputs,
            "input_fingerprint": fingerprint,
        }
    )
    prior = ApplicationVersion.objects.filter(pk=operation_id).first()
    if prior:
        if prior.snapshot_json != snapshot or str(prior.officer_id) != str(officer_id):
            raise ValueError("Conflicting application save retry.")
        return _saved(prior)
    latest = ApplicationVersion.objects.filter(case_id=case_id).first()
    if previous and (latest is None or str(latest.pk) != previous.application_id):
        raise ValueError("This application changed. Reopen the latest version before saving.")
    version = latest.version + 1 if latest else 1
    candidate = SavedApplication(
        str(operation_id), case_id, version, timezone.now().isoformat(), snapshot
    )
    scope = CaseScope(
        str(officer_id), None, case_id, version, timezone.localdate(), str(operation_id)
    )
    get_case(
        scope, lambda key: candidate
    )  # Validate snapshot shape without requiring completeness.
    row = ApplicationVersion.objects.create(
        application_id=operation_id,
        case=state,
        officer_id=officer_id,
        version=version,
        snapshot_json=snapshot,
    )
    state.fingerprint = fingerprint
    state.revision += 1
    state.save(update_fields=["fingerprint", "revision"])
    return _saved(row)
