# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated binding for the single-case demo; no model or MCP dependency."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.utils import timezone

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.application.assess_saved_case import Calculation, assess_cashflow
from farmcredit.application.get_case import CaseBrief, CaseScope, get_case
from farmcredit.application.get_records import CaseRecords, get_records
from farmcredit.application.stress_scenarios import StressAssumptions

# Replace this explicit demo scope with institution membership before real case imports.
DEMO_CASE_ID = "FC-001"


def _require_officer(officer_id: str):
    user = get_user_model().objects.filter(pk=officer_id, is_active=True).first()
    if (
        user is None
        or not user.get_full_name().strip()
        or not user.has_perm("auth.review_assessment")
    ):
        raise PermissionError("A named, authorised officer is required to access this case.")
    return user


@dataclass(frozen=True)
class BoundCaseReader:
    scope: CaseScope

    def _require_access(self) -> None:
        _require_officer(self.scope.officer_id)
        if self.scope.case_id != DEMO_CASE_ID:
            raise PermissionError("This workspace only authorises the demo case.")

    def get_case(self) -> CaseBrief:
        """No case selector is exposed to the future tool caller."""
        self._require_access()
        return get_case(self.scope, AssessmentStore().get)

    def assess_cashflow(self, assumptions: StressAssumptions) -> Calculation:
        self._require_access()
        return assess_cashflow(self.scope, AssessmentStore().get, assumptions)

    def get_records(self, categories: tuple[str, ...]) -> CaseRecords:
        """Recheck access and retrieve only records from the bound saved version."""
        return get_records(self.get_case(), categories)


def bind_case_reader(*, officer_id: str, assessment_id: str) -> BoundCaseReader:
    """officer_id must come from the authenticated session, not tool arguments."""
    _require_officer(officer_id)
    saved = AssessmentStore().get(assessment_id)
    if saved is None:
        raise LookupError("Saved case version not found.")
    if saved.case_id != DEMO_CASE_ID:
        raise PermissionError("This workspace only authorises the demo case.")
    return BoundCaseReader(
        CaseScope(
            str(officer_id), saved.assessment_id, saved.case_id, saved.version, timezone.localdate()
        )
    )
