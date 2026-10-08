# Product scope and workflow

FarmCredit helps a named officer turn an incomplete agricultural credit application
into a sourced advisory or a specific request for evidence. The agent chooses which
permitted records to investigate; deterministic code checks repayment cash flow.
The officer reviews the advisory. The lender retains the loan decision.

[README](../README.md) owns setup, demonstration-data disclosure and attribution.
[ARCHITECTURE](../ARCHITECTURE.md) owns implementation boundaries and execution limits.
This document owns current product behaviour and the decisions behind it, rather
than a chronological implementation log.

## People and scope

Uzima Havillah is the proposed workflow context. Its exact extension-office/cooperative
roles and intended-user approval arrangement have not been validated. The household
is the beneficiary; cooperatives, SACCOs and microfinance institutions are potential
record providers, not interchangeable systems or confirmed partners.

The prototype accepts named crops and enterprises, cooperative names and Kenyan
market/weather locations. The deterministic calculator supports one harvest sold in
kilograms with supplied financing terms; recurring sales, livestock and mixed
enterprises require an appropriate cash-flow model and remain evidence requests.
Applications are owned by their creating officer. Cooperative naming does not add
institution-wide access, a provider connection or a lender policy; supplied
institutional files remain the available record adapter. Without a linked file, no
demonstration policy is attached; the institution’s own policy and records must be
obtained before a financial assessment. It accepts incomplete intake and
explicit seasonal or instalment repayment schedules. The linked institution file is
selected explicitly; a household's name never guesses the match.

In scope:

- Immutable application versions, including missing inputs and source gaps.
- Institutional repayment history, obligations, savings restrictions and supplied policy.
- Selected market/weather evidence, with source and coverage limitations.
- Model-selected tool use, deterministic calculations and cited drafts.
- Named advisory review, change requests, history and failure recovery.

Outside this version: real lender integrations, institution-wide access sharing,
farmer messages, credit flags, loan approval, disbursement, input orders, interest
schedule generation, other crop/livestock models and validated credit scoring.
Do not imply those actions occurred when responding to an unsupported request.

## Officer journey

Applications is the single primary navigation destination. The site root and the
old saved-assessment list redirect there. The earlier shared household calculator,
assessment detail, save and review web endpoints are retired: they expose no stored
records and accept no writes. Historical records remain intact. Saved applications,
findings and review history remain available within the owning officer's application;
creating another officer account does not grant access to those applications.

1. **Meet the case.** Sign-in opens Applications unless an explicit return destination
   was requested. The case preview explains the household's request, the officer's
   role and the value of investigation. Optional cards explain the records. Opening
   the workspace saves the application only.
2. **Ask.** Suggested questions fill the composer; only Send to agent starts inference.
   A request is limited to 1,000 characters and saved with the run. The agent must
   address the request while respecting mandatory evidence and approval boundaries.
3. **Investigate.** One current recorded action, elapsed time and recent returned
   checks take focus. Detailed activity opens on request. Returned evidence can still
   be missing or incompatible; tool completion does not mean eligibility.
4. **Understand the finding.** Open questions lead even when calculated cash flow has
   no gap. The finding distinguishes unavailable calculations from zero, displays
   cash remaining under the assumptions and directs the officer to review.
5. **Review.** Inspect the finding, unresolved questions and optional supporting
   evidence. Approve the exact advisory or request changes with a reason. The UI
   confirms the saved reviewer, time and outcome. An evidence request has its own
   approval label. None of these states means a loan was approved or declined.
6. **Continue.** Each open question offers “Answer this”, which adds its context to
   the visible composer without discarding a typed answer. Include source and date.
   Chat answers remain officer-provided claims; changing calculation inputs requires
   a saved application version. While a run is active, the officer can draft the next
   request in the same tab. It is restored after completion, never sent automatically,
   and does not interrupt or steer the active model call. Follow-ups use the previous
   completed model response on the same
   application version as context, not fresh evidence. Each follow-up is another
   investigation. Change facts through Application details and save a new version.
   Older drafts and decisions remain readable but cannot be approved as current.

New application intake groups household, harvest, financing, cash, sources and
optional evidence references into expandable sections, with a definition beside
each field. Unknown amounts stay blank; zero is an explicit value. Save and return
later confirms the save in Applications, where Continue editing reopens the saved
facts. Save and open agent workspace saves without inference; Send to agent remains
the explicit handoff. Unsaved edits trigger a browser departure warning. Field
errors retain entered values and open the affected section, with linked error
summaries. This follows Apple's [data-entry guidance](https://developer.apple.com/design/human-interface-guidelines/entering-data)
through progressive disclosure, visible labels and appropriate input types.

The latest eight requests appear in the conversation; older runs remain in History.
Case details and history open on demand, with Close, Escape and focus restoration.
Without JavaScript, their links reach inline disclosures. Validation reveals hidden
invalid fields. Sources and other deep links reveal containing disclosures.

The separate fixed evidence check offers a comparison using the same tools without
model selection. The guided repayment calculator illustrates timing and price
changes without saving a case or invoking a model; it is not the primary agent demo.

## Evidence and calculation rules

An application records household/farm context, crop and season, expected harvest,
retained quantity, losses, assumed sale price and date, financing principal/charges,
explicit repayments, opening cash, dated cash movements and source metadata.
Incomplete records can be saved; missing critical evidence prevents calculation.

- Unknown amounts are not zero. An explicit empty obligations file only describes
  that institution's recorded coverage; it does not prove there are no outside debts.
- Institutional checks request missing repayment history, flag unresolved arrears
  and reconcile institutional obligations with household cash records. These are
  review requirements, not an approval threshold or validated lender policy.
- Savings restrictions are visible. Savings are not automatically added to opening
  cash, and historical yields do not replace an expected harvest assumption.
- Saleable harvest is expected harvest minus retained quantity and losses. Inputs
  must use compatible units and describe distinct quantities.
- Supplier financing is a non-cash purchase. Do not invent household loan proceeds
  or charge the same financed purchase twice; include the eventual repayment once.
- Each supplied repayment must reconcile with principal and stated charges. Cash
  coverage must extend through the final repayment. Do not generate interest or
  infer missing fees, deductions or household expenses.
- Decimal calculations preserve every dated funding gap. A later surplus cannot
  cover an earlier missed payment. Ambiguous same-day receipt/payment ordering
  requires clarification.
- Price-only, harvest-only and combined stress scenarios use explicit reductions.
  The agent's 20% defaults are test assumptions, not forecasts or lender thresholds.
  Retained food and losses stay fixed; impossible quantities produce no result.
- Model prose cannot replace calculated totals. Sources must exist in returned
  evidence, and a calculation identifier is not a source citation.

The three built-in institutional files share the same cash-flow assumptions:

| File | Distinguishing evidence | Required behaviour |
| --- | --- | --- |
| Household A / `DEMO-001` | Complete institutional records | Calculate only if the remaining input and source checks pass |
| Household B / `DEMO-002` | Recorded unresolved arrears | Identify the officer-review requirement; do not claim lending approval |
| Household C / `DEMO-003` | Missing repayment history | Request the missing evidence rather than inventing history or affordability |

Market queries use the saved crop and location, not a maize/Nakuru default. KAMIS
resolves published county, market and commodity IDs; a variety/classification can
narrow ambiguous quotes. Ambiguous prices prompt clarification with the returned
classifications. HDX matches the exact crop and market. Neither substitutes another
commodity or treats unavailable coverage as a price. Weather resolves a Kenyan town
and checks returned coordinates against that reference; ambiguous locations need
clarification. Historical Nakuru references remain readable.

The agent investigates relevant selected external evidence even when institutional
records are missing, before saving the evidence request. It explains relevance to
the enterprise, location, grade and season, names the missing evidence and its likely
holder, and does not claim access to a cooperative merely because it is named.

Market observations retain date, place, commodity, units and wholesale/retail basis.
A retrieved quote is not necessarily current or comparable to a farm-gate assumption.
Weather preserves geography and forecast coverage; it cannot establish a future
harvest or justify a numerical yield adjustment without a validated method.
Unavailable evidence remains unavailable, even when a retrieval tool itself succeeds.

## Interaction and failure behaviour

The saved-case workspace explains that incomplete applications can be investigated.
Its expandable inventory groups actual saved cash, harvest and loan values, preserving
unknown values and evidence-basis labels. A linked institution file is not described
as verified. Live progress lists only requested evidence categories and their recorded
states; a returned record does not establish suitability.

The finding includes an expandable **evidence readiness** checklist: institutional
checks satisfied, no dated baseline cash gap, and no recorded open questions. The
count is a presentation of three recorded review checkpoints, not a credit score,
calibrated confidence or repayment probability. Any unresolved checkpoint keeps the
indicator at “Further review needed”; questions from deterministic source reviews
are included even if the model omits them. It describes that saved finding, not current
loan approval. Unchecked sources remain unverified.

Use the same Ask → Investigate → Review vocabulary across the workspace and review
page. Keep the next action clear; reveal source detail on request and keep the
follow-up composer visible after a finding. Preserve keyboard navigation, readable contrast, consistent spacing
and reduced-motion preferences. These choices follow Apple's guidance on
[feedback](https://developer.apple.com/design/human-interface-guidelines/feedback),
[disclosure](https://developer.apple.com/design/human-interface-guidelines/disclosure-controls)
and [progress](https://developer.apple.com/design/human-interface-guidelines/progress-indicators);
they are design principles, not a certification claim.

Progress displays committed events, never guessed percentages or invented activity.
Polling preserves expanded disclosures and keyboard focus. A rejected start stops
polling, displays the safe server explanation and preserves the request. If a run is
not confirmed within ten seconds, or updates fail, direct the officer to recorded
state before retrying. Interrupted updates are distinct from confirmed run failure.

The provider adapter distinguishes credential, credit, rate-limit and connection
failures. It interprets allowlisted metadata rather than exposing raw provider text.
A narrowly identified transient credit reservation may receive one bounded retry;
permanent funding/key problems remain failures. Exact start retries reuse their
signed run binding; new investigations can incur new charges. There is no durable
queue or automatic continuation after a process interruption.

Display wording helpers apply to source text, agent prose and trace copies. Stored
provenance, inputs and prior decisions remain unchanged. Keep demonstration-data
disclosure in README and retain assumption/observation/forecast labels in the UI.

## Verification and remaining work

Software tests cover arithmetic, evidence validation, officer isolation, signed
requests, immutable PostgreSQL records, concurrent edits, stale review prevention,
provider errors and MCP transport. Browser checks cover the complete case-to-review
journey, follow-ups, approval and change requests, keyboard access, source navigation,
connection failure, rejected starts and a 390-pixel viewport. Run the commands in
README before proposing code changes; passing local checks does not replace CI.

Hosted-model checks are separate from deterministic tests. On 7 October 2026, one
bounded live browser run completed six model requests and six tool calls in 43.7
seconds, saving a finding with an unresolved evidence question. Provider-reported
cost was USD 0.00499742. Earlier attempts included provider and draft-contract
failures; this successful run is not a reliability benchmark. Raw local traces are
not release documentation or evidence of intended-user validation.

On 8 October 2026, a live rice case for Ahero, Kisumu, retrieved a Pishori wholesale
quote dated 6 October and 168 hourly weather forecast records for Kisumu. A bounded
agent run with no linked institution completed four model/tool calls and saved an
evidence request for the named institution’s policy and terms, farm inputs, buyer
agreement and seasonal outlook. No institution policy or financial result was
invented. Provider-reported cost for that run was USD 0.00261769. This establishes
one tested non-maize/non-Nakuru path, not universal provider coverage or a reliability
benchmark. Tool categories are enumerated; review metadata is not a fetchable record.

Remaining product work includes intended-user testing, repeated representative
agent evaluation, production access/deployment design and source-policy validation.
Competition eligibility, required submission artefacts and publication requirements
must be checked against the organiser's current rules before claiming readiness.
