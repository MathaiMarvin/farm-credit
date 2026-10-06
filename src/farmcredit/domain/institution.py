# SPDX-License-Identifier: AGPL-3.0-only
"""Recorded institutional facts and deterministic review rules, independent of providers."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from farmcredit.domain.cashflow import CashMovement, validate_money
from farmcredit.domain.evidence import EvidenceIssue


def _money(value: Decimal) -> None:
    validate_money(value)
    if value < 0:
        raise ValueError("Recorded balances and repayment amounts cannot be negative.")


@dataclass(frozen=True)
class YieldRecord:
    record_id: str
    harvested_on: date
    gross_kg: Decimal
    area_hectares: Decimal

    def __post_init__(self):
        if type(self.harvested_on) is not date:
            raise ValueError("Yield history needs a harvest date.")
        for value in (self.gross_kg, self.area_hectares):
            if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
                raise ValueError("Yield history needs finite, nonnegative quantities.")
        if self.area_hectares == 0:
            raise ValueError("Recorded plot area must be positive.")


@dataclass(frozen=True)
class RepaymentRecord:
    record_id: str
    due_on: date
    due: Decimal
    paid: Decimal

    def __post_init__(self):
        if type(self.due_on) is not date:
            raise ValueError("Repayment history needs a due date.")
        _money(self.due)
        _money(self.paid)
        if self.due == 0 or self.paid > self.due:
            raise ValueError("Recorded payments must be between zero and the positive amount due.")


@dataclass(frozen=True)
class SavingsRecord:
    record_id: str
    balance: Decimal
    restricted: Decimal

    def __post_init__(self):
        _money(self.balance)
        _money(self.restricted)
        if self.restricted > self.balance:
            raise ValueError("Restricted savings cannot exceed the recorded balance.")


@dataclass(frozen=True)
class ObligationRecord:
    record_id: str
    cash_record_id: str
    due_on: date
    amount: Decimal

    def __post_init__(self):
        if type(self.due_on) is not date or not self.cash_record_id.strip():
            raise ValueError("An obligation needs its due date and cash-ledger record reference.")
        _money(self.amount)
        if self.amount == 0:
            raise ValueError("An obligation must have a positive amount.")


@dataclass(frozen=True)
class InstitutionFile:
    member_ref: str | None
    version: str
    source: str
    recorded_on: date
    yields: tuple[YieldRecord, ...] | None
    repayments: tuple[RepaymentRecord, ...] | None
    savings: SavingsRecord | None
    obligations: tuple[ObligationRecord, ...] | None
    synthetic: bool = True

    def __post_init__(self):
        if (
            not self.version.strip()
            or not self.source.strip()
            or type(self.recorded_on) is not date
        ):
            raise ValueError("Institution records need a version, source and recording date.")
        if self.synthetic is not True:
            raise ValueError("Only synthetic institution records are supported.")
        for field in ("yields", "repayments", "obligations"):
            if getattr(self, field) is not None:
                object.__setattr__(self, field, tuple(getattr(self, field)))
        rows = (
            *self.yields_or_empty,
            *(self.repayments or ()),
            *(self.obligations or ()),
            *((self.savings,) if self.savings else ()),
        )
        ids = [row.record_id for row in rows]
        if any(not key.strip() or key != key.strip() for key in ids) or len(set(ids)) != len(ids):
            raise ValueError("Institution record identifiers must be nonblank and unique.")
        if any(row.harvested_on > self.recorded_on for row in self.yields_or_empty):
            raise ValueError("Historical harvests cannot follow the source recording date.")
        if any(row.due_on > self.recorded_on for row in self.repayments or ()):
            raise ValueError("Repayment history cannot contain future instalments.")
        references = [row.cash_record_id for row in self.obligations or ()]
        if len(set(references)) != len(references):
            raise ValueError("Each institutional obligation needs a distinct ledger reference.")

    @property
    def yields_or_empty(self):
        return self.yields or ()


@dataclass(frozen=True)
class ReviewPolicy:
    policy_id: str
    version: str
    source: str
    effective_on: date
    rules: tuple[str, ...]
    synthetic: bool = True

    def __post_init__(self):
        supported = {
            "repayment_history_required",
            "arrears_need_review",
            "obligations_must_reconcile",
        }
        object.__setattr__(self, "rules", tuple(self.rules))
        if not all(
            isinstance(v, str) and v.strip() for v in (self.policy_id, self.version, self.source)
        ):
            raise ValueError("A supplied policy needs an identity, version and source.")
        if type(self.effective_on) is not date or self.synthetic is not True:
            raise ValueError("Only explicitly dated synthetic policies are supported.")
        if (
            not self.rules
            or not set(self.rules) <= supported
            or len(set(self.rules)) != len(self.rules)
        ):
            raise ValueError("The supplied review policy contains unsupported or duplicate rules.")
        if "arrears_need_review" in self.rules and "repayment_history_required" not in self.rules:
            raise ValueError("Arrears review requires explicit repayment-history coverage.")


@dataclass(frozen=True)
class PolicyCheck:
    rule: str
    status: str
    finding: str
    record_ids: tuple[str, ...]


@dataclass(frozen=True)
class InstitutionReview:
    status: str
    checks: tuple[PolicyCheck, ...]
    arrears: Decimal | None
    cashflow_issues: tuple[EvidenceIssue, ...]
    questions: tuple[str, ...]
    limitations: tuple[str, ...]


def review_institution(
    file: InstitutionFile,
    policy: ReviewPolicy,
    *,
    as_of: date,
    starts_on: date | None,
    ends_on: date | None,
    movements: tuple[CashMovement, ...],
) -> InstitutionReview:
    """Review source coverage and supplied rules; never approve a loan or add savings to cash."""
    checks, issues, questions = [], [], []
    usable = file.recorded_on <= as_of
    if not usable:
        questions.append(
            "Provide institutional records recorded on or before the evidence review date."
        )
    if policy.effective_on > as_of:
        return InstitutionReview(
            "evidence_required",
            (),
            None,
            (),
            ("Provide a demo review policy effective on the evidence review date.",),
            ("No eligibility finding is available under a future policy.",),
        )
    repayments = file.repayments if usable else None
    arrears = (
        sum((row.due - row.paid for row in repayments if row.due_on < file.recorded_on), Decimal(0))
        if repayments
        else None
    )
    for rule in policy.rules:
        if rule == "repayment_history_required":
            if repayments:
                checks.append(
                    PolicyCheck(
                        rule,
                        "satisfied",
                        "Repayment history is present in the supplied institutional file.",
                        tuple(row.record_id for row in repayments),
                    )
                )
            else:
                checks.append(
                    PolicyCheck(
                        rule,
                        "evidence_required",
                        "Repayment history is unavailable; a clean repayment record cannot be assumed.",
                        (),
                    )
                )
                questions.append(
                    "Request repayment history, or confirm that this household has no prior borrowing and needs officer review."
                )
        elif rule == "arrears_need_review":
            ids = tuple(row.record_id for row in repayments or () if row.due - row.paid > 0)
            if arrears is None:
                checks.append(
                    PolicyCheck(
                        rule,
                        "evidence_required",
                        "Arrears status is unknown without repayment history.",
                        (),
                    )
                )
            elif arrears > 0:
                checks.append(
                    PolicyCheck(
                        rule,
                        "officer_review",
                        f"KES {arrears:.2f} is recorded in arrears. The supplied demo rule requires officer review.",
                        ids,
                    )
                )
                questions.append(
                    "Resolve the recorded arrears and confirm repayment timing before relying on a complete affordability finding."
                )
                issues.append(
                    EvidenceIssue(
                        "institution.arrears",
                        "Outstanding arrears need confirmed repayment timing; they are not silently omitted or added to the proposed loan.",
                        ids,
                    )
                )
            else:
                checks.append(
                    PolicyCheck(
                        rule,
                        "satisfied",
                        "No arrears are recorded in the supplied repayment history; this does not cover other lenders.",
                        tuple(row.record_id for row in repayments),
                    )
                )
        elif rule == "obligations_must_reconcile":
            obligations = file.obligations if usable else None
            ids = tuple(row.record_id for row in obligations or ())
            before = len(issues)
            if obligations is None:
                checks.append(
                    PolicyCheck(
                        rule,
                        "evidence_required",
                        "Current institutional obligations are not recorded; they are not assumed to be zero.",
                        (),
                    )
                )
                questions.append(
                    "Request the institution's current obligations and their dated repayment terms."
                )
                continue
            if starts_on is None or ends_on is None:
                checks.append(
                    PolicyCheck(
                        rule,
                        "evidence_required",
                        "The assessment dates and supplied schedule are needed to reconcile obligations.",
                        ids,
                    )
                )
                continue
            for row in obligations:
                if row.due_on > ends_on:
                    continue
                matching = tuple(m for m in movements if m.record_id == row.cash_record_id)
                if row.due_on < starts_on:
                    reason = "An outstanding obligation predates the cash-flow window; confirm its repayment timing."
                elif (
                    len(matching) != 1
                    or matching[0].on != row.due_on
                    or matching[0].amount != -row.amount
                ):
                    reason = f"Reconcile {row.cash_record_id}: KES {row.amount:.2f} due {row.due_on.isoformat()} with the supplied household cash records."
                elif any(
                    m.record_id != row.cash_record_id
                    and m.on == row.due_on
                    and m.amount == -row.amount
                    for m in movements
                ):
                    reason = f"Possible duplicate of {row.cash_record_id}; confirm whether equal dated payments are distinct obligations."
                else:
                    continue
                issues.append(EvidenceIssue("institution.obligations", reason, (row.record_id,)))
                questions.append(reason)
            checks.append(
                PolicyCheck(
                    rule,
                    "evidence_required" if len(issues) > before else "satisfied",
                    "Recorded obligations need reconciliation with the cash ledger."
                    if len(issues) > before
                    else "Recorded institutional obligations within the assessment window reconcile once to the supplied cash ledger.",
                    ids,
                )
            )
    if not file.yields or not usable:
        questions.append(
            "Historical yields are unavailable; confirm the evidence basis for expected harvest without inventing a past yield."
        )
    if file.savings is None or not usable:
        questions.append("Request the savings balance and any restrictions; no balance is assumed.")
    statuses = {check.status for check in checks}
    status = (
        "officer_review"
        if "officer_review" in statuses
        else "evidence_required"
        if questions or "evidence_required" in statuses
        else "checks_satisfied"
    )
    return InstitutionReview(
        status,
        tuple(checks),
        arrears,
        tuple(issues),
        tuple(dict.fromkeys(questions)),
        (
            "These are illustrative demo review rules, not validated lending criteria or a credit score. The lender retains the decision.",
            "Savings, including unrestricted deposits, are not added to opening cash without separate evidence of an available cash transfer.",
            "Historical yields do not replace the officer's expected harvest assumption.",
            "Institution records do not establish that debts held elsewhere are absent; coverage is limited to the recorded file date.",
        ),
    )
