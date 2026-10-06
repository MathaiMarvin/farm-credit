# SPDX-License-Identifier: AGPL-3.0-only
"""Authenticated application and historical demo bindings; no model or MCP dependency."""

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.utils import timezone

from farmcredit.adapters.assessment_store import AssessmentStore
from farmcredit.adapters.institution_demo import policy_is_current, snapshot_institution
from farmcredit.application.assess_saved_case import Calculation, assess_cashflow
from farmcredit.application.get_case import CaseBrief, CaseScope, get_case
from farmcredit.application.get_records import CaseRecords, get_records
from farmcredit.application.institution_evidence import assess_institution
from farmcredit.application.market_evidence import assess_market
from farmcredit.application.stress_scenarios import StressAssumptions
from farmcredit.application.weather_evidence import assess_weather

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
        if self.scope.application_id:
            saved = self.read_saved(self.scope.application_id)
            if saved.case_id != self.scope.case_id or saved.version != self.scope.version:
                raise PermissionError("Application binding changed.")
            return
        if self.scope.case_id != DEMO_CASE_ID:
            raise PermissionError("This workspace only authorises the demo case.")

    def read_saved(self, input_id):
        if self.scope.application_id:
            from farmcredit.adapters.application_store import get_application

            return get_application(input_id, self.scope.officer_id)
        return AssessmentStore().get(input_id)

    def get_case(self) -> CaseBrief:
        """No case selector is exposed to the future tool caller."""
        self._require_access()
        return get_case(self.scope, self.read_saved)

    def assess_cashflow(self, assumptions: StressAssumptions) -> Calculation:
        self._require_access()
        return assess_cashflow(self.scope, self.read_saved, assumptions)

    def get_institution(self):
        self._require_access()
        if not self.scope.institution_snapshot_json:
            return None
        inputs = self.read_saved(self.scope.input_id).snapshot["inputs"]
        return assess_institution(
            self.scope.institution_snapshot_json, inputs, as_of=self.scope.evidence_as_of
        )

    def get_market(self):
        self._require_access()
        if not self.scope.market_snapshot_json:
            return None
        return assess_market(
            self.scope.market_snapshot_json,
            self.read_saved(self.scope.input_id).snapshot["inputs"],
            as_of=self.scope.evidence_as_of,
        )

    def get_kamis(self):
        self._require_access()
        if not self.scope.kamis_snapshot_json:
            return None
        return assess_market(
            self.scope.kamis_snapshot_json,
            self.read_saved(self.scope.input_id).snapshot["inputs"],
            as_of=self.scope.evidence_as_of,
            reference_field="kamis_market_reference",
        )

    def get_weather(self):
        self._require_access()
        if not self.scope.weather_snapshot_json:
            return None
        return assess_weather(
            self.scope.weather_snapshot_json,
            self.read_saved(self.scope.input_id).snapshot["inputs"],
            as_of=self.scope.evidence_as_of,
        )

    def require_current_policy(self):
        if self.scope.institution_snapshot_json and not policy_is_current(
            self.scope.institution_snapshot_json
        ):
            raise ValueError(
                "The demo review policy changed. Start a new investigation before drafting or reviewing."
            )

    def get_records(self, categories: tuple[str, ...]) -> CaseRecords:
        """Recheck access and retrieve only records from the bound saved version."""
        return get_records(
            self.get_case(),
            categories,
            institution=self.get_institution(),
            market=self.get_market(),
            kamis=self.get_kamis(),
            weather=self.get_weather(),
        )


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


def bind_application_reader(*, officer_id: str, application_id: str) -> BoundCaseReader:
    from farmcredit.adapters.application_store import get_application

    saved = get_application(application_id, officer_id)
    return BoundCaseReader(
        CaseScope(
            str(officer_id),
            None,
            saved.case_id,
            saved.version,
            timezone.localdate(),
            saved.application_id,
            snapshot_institution(
                saved.snapshot["inputs"].get("institution_record_set") or None,
                retrieved_at=timezone.now(),
            ),
        )
    )
