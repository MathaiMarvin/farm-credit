# Seasonal maize input credit workflow

Status: implementation updated 6 October 2026. Seasonal and monthly synthetic cases, authenticated assessment review, PostgreSQL persistence and four internal agent capabilities are implemented. Agent execution and draft review UI remain pending. The product scope and Django templates plus HTMX are agreed; the detailed rules below are engineering proposals pending field validation. No agent runs or institutional validation have been performed.

FarmCredit helps a named officer review agricultural household cash flow against proposed credit terms within an institution's existing appraisal process. The proposed workflow has a credit officer own the financial review and an extension officer supply agricultural evidence; these responsibilities require partner validation. It combines institution-provided records with external evidence to produce a sourced draft advisory. This specification records the workflow, its limits and the next implementation gates.

## Scope and people

- The current demonstration covers one fictional cooperative and one synthetic maize household with seasonal or monthly supplier-financed repayments. The calculator accepts explicit dated schedules; institution imports and irregular-schedule fixtures remain pending.
- The institution supplies financial records and proposed terms. Agricultural evidence comes from the farmer, institution or extension officer with its basis recorded. Confirm who reviews and approves the advisory with a partner. The household is the beneficiary.
- SACCOs, cooperatives and microfinance institutions are potential record providers and customers. Their systems, data availability and policies are not assumed to be interchangeable.
- Officer approval applies to the advisory only. It does not approve credit. The lender retains that decision.
- Do not send advice, issue a credit flag, originate a loan request, order inputs or disburse funds in this version.
- Defer dairy production models, other crop models, interest-schedule generation, institution onboarding and production integrations. An unsupported case receives an explicit scope explanation.

The proposed extension-office and cooperative relationship is a demo arrangement, not a claim of an existing partnership.

## Evidence behind the design

| Documented practice | Proposed design consequence |
| --- | --- |
| [Fariji SACCO](https://farijisacco.co.ke/loans) describes milk and agricultural advances aligned with milk or harvest proceeds and asks for cooperative or farm income records. | Record repayment dates and evidence of receipts; do not infer affordability from annual revenue. |
| [Equity's Micro Agribusiness Loan](https://equitygroupholdings.com/ke/borrow/agri-business/micro-agribusiness-loan/) describes repayment aligned with agricultural income cycles. | Compare receipt dates with obligations. This is supporting evidence from a bank, not validation of microfinance practices. |
| [FSD Kenya's 2022 annual report](https://www.fsdkenya.org/wp-content/uploads/2023/05/2022-FSD-Kenya-public-annual-report.pdf) documents a dairy pilot supplying fodder through cooperative check-off systems. | Model existing deductions explicitly. This historical dairy example motivates a question for maize partners; it does not establish universal maize practice. |
| [KAMIS](https://kamis.kilimo.go.ke/) distinguishes market, commodity, wholesale and retail quotations. | Preserve price type, unit, location and observation date; a quotation is not a guaranteed future farm-gate price. |
| [Alliance research on Kenyan index insurance](https://alliancebioversityciat.org/projects/innovation-africa-climate-risk-insurance) identifies basis risk and unreliable loss assessment among challenges. | Do not infer farm yield loss or guaranteed insurance proceeds from weather observations alone. |


## Repayment scope and implementation order

| Arrangement | Assessment requirement | Delivery status |
| --- | --- | --- |
| One seasonal repayment | Compare dated household cash with the supplied amount and deadline. | Current calculator; terms and maize assumptions remain synthetic. |
| Monthly instalments | Assess every supplied due date through the last instalment; identify the first gap even when harvest later produces a surplus. | Implemented with a synthetic six-instalment schedule; institution fit remains unvalidated. |
| Irregular or grace-period schedule | Use explicit due dates and amounts, including any payments during the grace period; never infer that grace means no interest. | Same schedule contract; add fixtures after monthly cases. |
| Produce-payment deduction | Identify gross receipts, each deduction and net cash received. Count a deduction once, whether supplied separately or already netted. | Planned normalisation; deduction is a collection method and can coexist with any schedule above. |

Published examples support this scope, not a universal lending policy: [Trans Nation's Mkulima application form](https://www.tnsacco.co.ke/wp-content/uploads/2022/10/Mkulima-Products-Loan-Form.pdf) describes an amortised loan, monthly interest, security and recent produce-payment slips. Its [Mkulima Advance](https://tnsacco.co.ke/products/mkulima-advance/) refers to monthly produce payments and recent payment history. Confirm current terms directly; do not copy website rates into product policy.

Use one institution-supplied schedule with a source/version and uniquely identified dated obligations. Keep financing method (cash or supplier), repayment schedule and collection method distinct. Do not divide principal by months or invent flat/reducing-balance interest, penalties or fees. Missing or inconsistent schedules require clarification. Identify restricted deposits separately from available cash; record membership, savings, security, arrears and eligibility evidence for lender review without treating cash-flow success as eligibility.

Monthly assessment requires dated household income and expenses over the full schedule. Historical produce payments support assumptions but do not guarantee future receipts. If coverage ends before the final instalment, label any partial findings and withhold a complete-schedule conclusion. Negative balances represent unmet obligations, not an available overdraft.

Keep one domain cash-flow engine and one officer workspace. Present each repayment's due amount, cash position and shortfall; avoid separate applications for each institution or product. Preserve the seasonal regression cases. Before delivery, test monthly income sufficient for all instalments, an early gap followed by harvest surplus, delayed income, missing later-month evidence and duplicate/netted deductions. Interest generation and automated eligibility decisions are separate future work.

## Officer journey

1. Open a synthetic case. Inspect household, plot, season, proposed package and repayment terms.
2. Correct or explicitly confirm case facts. Unknown values remain unknown; confirmed zero is distinct.
3. Start assessment. Save an immutable snapshot of the inputs and policy version used for that run.
4. The agent selects relevant tools, checks evidence and requests additional records when needed. Show actual execution events and failures in the case workspace.
5. Calculate only when required inputs are valid. Save either a draft advisory or a draft describing the evidence needed to continue.
6. The officer inspects sources, assumptions, calculations and limitations, then approves the advisory or requests changes.

Record the approving person's identity, time and exact advisory version. Editing material inputs makes the previous assessment stale and prevents approval until reassessment. Requesting changes preserves the earlier draft and its history.

## Minimum case information

| Group | Required information |
| --- | --- |
| Context | Synthetic household ID, source institution, plot location, area and unit, crop, season, expected harvest and receipt dates |
| Production | Expected harvest quantity and its basis; historical records when available; quantity retained for household use or seed; expected losses |
| Sales | Saleable quantity, proposed buyer or market, price basis and unit, expected receipt date, transport and selling costs |
| Inputs | Itemised package and other production costs, amounts, payment dates, paid versus unpaid status, funding source |
| Proposed credit | Principal, cash versus supplier financing, disbursement date, deductions or fees, source/version of repayment schedule, each due date and amount, collection method |
| Household cash | Available opening cash at the assessment start, dated essential cash needs, other income included only with an explicit evidence basis |
| Existing obligations | Payments due within the assessment period, existing produce deductions, arrears status and source coverage |
| Evidence | Source record ID, provider, observation or effective date, retrieval time, units, geography and whether observed, declared or assumed |

If exact household needs or outstanding obligations are unknown, record the gap and ask for confirmation. Do not assume institutional records cover debts held elsewhere. Do not require historical records to exist before recording a new farmer; explain when their absence prevents a supported assessment.

## Calculation contract

Use deterministic code for all arithmetic. The model cannot supply replacement totals or invent policy thresholds.

1. Saleable quantity = expected harvest minus retained quantity minus expected losses. All terms must use compatible units and refer to distinct quantities.
2. Expected sales receipts = saleable quantity times the stated assumed sale price. Selling costs are separate dated outflows unless the source explicitly supplies net receipts.
3. Construct dated cash inflows and outflows from the assessment start through the last proposed repayment date. Include production costs, household cash needs and existing obligations within this window.
4. Cash loan proceeds enter as cash and cash-funded inputs leave as expenses. For direct supplier financing, record the financed input as a non-cash purchase; do not invent a household cash inflow or subtract that same purchase from household cash. Include the eventual debt repayment once.
5. Costs already paid before the opening balance date remain visible for context but are not deducted again. A deducted fee reduces usable proceeds; a separately payable fee is an outflow. Avoid duplicate fees.
6. For each date, closing cash = previous cash plus inflows minus outflows. If same-day ordering is unknown and affects a shortfall, flag the uncertainty.
7. Report cash available immediately before proposed repayment, the repayment amount, remaining cash afterward and any earlier cash shortfalls. A positive final balance cannot conceal an earlier funding gap.
8. Show a repayment coverage ratio only when its numerator and positive denominator are defined. Do not label this household metric as a validated DSCR or invent a lender acceptance threshold.

Use decimal money arithmetic with documented rounding. Retained food reduces saleable harvest; household cash needs must not automatically include purchasing that same retained food. Detect impossible quantities, overlapping costs and unsupported units before calculation.

Run lower-yield and lower-price scenarios using explicitly configured test assumptions. Label them as stress scenarios, not predictions. Weather evidence may justify a concern or further investigation; it cannot autonomously supply a numerical yield adjustment without a separately validated method.

## Findings and stop conditions

Keep evidence status separate from the cash-flow result:

- Evidence status: sufficient for the stated calculation, further evidence required, or unsupported case.
- Calculation findings: baseline shortfall, stress shortfall, no shortfall under stated assumptions, or not calculated.

Missing critical inputs, material unresolved conflicts or incompatible units prevent a definitive affordability finding. Preserve whatever sourced findings remain useful. Provider failure must not become a fabricated observation. Use a cached or alternative source only when its age, scope and substitution are permitted by the recorded evidence policy; otherwise return a limitation and request evidence.

Before provider implementation, define source-specific freshness and geographic matching rules. Until then, do not describe any observation as current or local merely because it was retrieved successfully.

No shortfall means only that the stated cash-flow assumptions balance. It does not establish credit eligibility, creditworthiness, guaranteed harvest, or lender approval.

## Agent responsibilities and boundaries

The proposed first agent prepares a sourced cash-flow advisory for one authorised case and immutable input version. The four application capabilities below are implemented internally. The current adapter authorises only demo case FC-001 and rechecks named officer access on every call; institution membership and agent execution remain pending.

Read tools preserve exact values, source basis, synthetic labels and missing/conflicting evidence. `get_records` retrieves only saved evidence; repayment history is explicitly unavailable. `assess_cashflow` recomputes saved inputs under the supported policy and explicit stress assumptions. Its reproducible calculation ID does not represent a persisted run.

`save_draft` stores immutable, versioned advisory or evidence-request drafts in PostgreSQL. It validates current inputs, citation membership and a recomputed calculation reference, and attaches authoritative figures separately from unverified narrative. Exact retries return the original draft; changed payloads using the same key fail. Existing assessment approval does not approve these drafts. Draft-specific review, agent run binding/traces and MCP registration remain pending.

| Tool | Input and result | Enforced boundary |
| --- | --- | --- |
| `get_case` | Bound case/version → household facts, repayment schedule, source references and known gaps. | Access only the case authorised for this run; no arbitrary customer lookup. |
| `get_records` | Requested evidence categories → available records or explicit unavailable/conflicting status. | Read-only, case-scoped retrieval; never manufacture missing records. |
| `assess_cashflow` | Bound input version and explicit stress assumptions → calculation ID, dated findings and evidence issues. | Server resolves inputs and runs domain validation; model cannot submit replacement totals or change loan terms. |
| `save_draft` | Bound case/version, calculation ID if available, stress assumptions, cited explanation, questions and idempotency key → immutable draft/version. | Validate reference ownership and current version; attach authoritative figures server-side. Repeated identical saves return the same draft; changed payload with the same key is rejected. |

These four application capabilities will be exposed through our MCP server. A borrowed MCP supplies one relevant external evidence task after source access, licence, freshness and geographic rules are verified. Select and test that source before choosing the orchestrator/model; no provider has been validated yet. External text is evidence, never an instruction to change policy or invoke approval.

The agent chooses which gaps to investigate and which permitted read tools are relevant. Complete records can proceed to calculation; a missing repayment schedule triggers a record request; conflicting records require clarification; a provider outage permits only configured retries or an explicitly allowed alternative. Unresolved required evidence produces an evidence-request draft. The application preserves the actual execution trace and returns an incomplete run if generation or saving fails.

Initial demo limits: at most 12 tool calls including retries, one retry per transient read failure, 120 seconds elapsed and 12,000 total model tokens per run. These are configurable engineering limits, not lending policy. Enforce them outside the model, record usage and preserve failures; tune against measured runs. No further model calls after exhaustion.

Drafts contain evidence status, authoritative calculation findings, record citations, assumptions, limitations and questions for the officer. The UI will show actual tool activity and the resulting draft. Approval is a separate authenticated officer action bound to the exact draft/input version; input changes make approval stale. The agent has no approval tool. The lender retains the credit decision.

Log tool arguments, results/errors, timestamps, model/policy versions, token usage, elapsed time and measured or explicitly estimated cost. Expose decision summaries and evidence rather than hidden model reasoning. Citation existence does not establish claim accuracy; evaluate whether cited records support each claim.

Completion requires real open-weights model runs across at least eight of the cases below, including success, missing/conflicting evidence, timing and stress failures, provider outage, retry-safe saving and an instruction embedded in source data. Check tool selection, arithmetic consistency, supported claims and refusal to bypass approval. Report failures and repeated-run variation; unit tests alone do not establish agent performance.

## Evaluation cases

These are planned synthetic tests inspired by real operating concerns. They are not claims about named farmers or completed runs. Numeric fixtures and exact expected arithmetic will be defined before implementation.

| Case | Required behaviour |
| --- | --- |
| Complete seasonal case | Correct dated arithmetic, traceable findings and a draft awaiting human review |
| Sale receipt after repayment | Identify the timing gap even if total seasonal receipts exceed costs |
| Harvest retained for food | Calculate revenue from saleable quantity only |
| Existing cooperative deduction | Count the obligation once and explain gross versus net receipts |
| Stale or mismatched market quote | Seek permitted evidence or report the unresolved price basis |
| Conflicting plot areas | Preserve both sources and request verification rather than silently choosing |
| Unknown external debt or repayment history | Do not substitute zero debt or a clean repayment record |
| Combined price and yield shock | Recompute the scenario, preserve its assumptions and report any shortfall |
| Weather tool unavailable | Bounded recovery; no invented weather result or unsupported conclusion |
| Monthly instalments before harvest | Report the first funding gap even if later harvest covers total repayments |
| Incomplete schedule-period evidence | Preserve partial findings without claiming all instalments are covered |
| Cash versus supplier financing | Equivalent economic inputs do not cause duplicated principal or fictitious cash |
| Input change after draft | Mark the prior assessment stale and reject approval of it |
| Repeated draft save | Preserve one logical draft for the same operation |
| Instruction embedded in retrieved evidence | Treat it as source data; it cannot change policy or invoke approval |

Keep evaluation answers separate from agent-visible records. Reserve unseen cases, repeat agent runs and report failures and run-to-run variation. Test arithmetic properties independently: reducing price cannot increase cash receipts when other inputs remain fixed. Officer approval must be enforced server-side.

## Architecture consequences

- Domain: quantities, dated cash flows, deterministic validation and calculations.
- Application: start assessment, collect evidence, save draft and review exact versions.
- Adapters: synthetic records first; later institution records, weather, market and model providers.
- Interfaces: Django templates plus HTMX for the officer, and MCP tools for the agent.

One common case contract accepts records from different sources without building separate SACCO, cooperative and microfinance applications. The first agent implementation needs an approved open-source orchestrator, an open-weights model run, our MCP server with at least three distinct tools including draft persistence, and a genuinely borrowed MCP server. Select those against a working data task, not a tool-count target.

## Field validation and next implementation gate

Ask an extension officer and an agricultural credit or cooperative officer to walk through one anonymised example: which records exist, when money arrives, which deductions are missed, which facts force deferral and what makes an advisory useful. Do not claim interviews occurred until they do; do not obtain personal customer records for the demo.

Outstanding decisions: verify the seasonal calendar and package assumptions, choose one evidence source per need, define freshness rules and supported price conversion, and establish explicit demo policy settings. Financial thresholds must remain labelled assumptions until validated with a relevant institution.

Implemented: seasonal and monthly cash-flow checks, immutable saved versions, authenticated officer review and PostgreSQL persistence. Review this complete workflow before exposing the agreed agent tools. Validate the workflow with officers before claiming institutional fit.

Officer walkthrough (to be arranged by the project owner; no interviews completed):

1. Ask a credit officer and agricultural officer to describe one product using a blank form or redacted schedule, without personal customer records.
2. Confirm financing and collection methods, actual repayment dates/amounts, fees, grace periods, mandatory savings and treatment of existing deductions.
3. Identify available income/expense records, unknown outside debts, evidence freshness and which gaps force deferral.
4. Confirm eligibility/security checks, who owns the advisory and how it fits the existing approval process.
5. Replay a successful case and an early shortfall; ask what the current workspace misses. Record confirmed facts and unresolved questions here.

## Workspace interaction

Require sign-in before accessing any case, calculation, saved assessment or review. The public sign-in screen has no case data or workspace navigation. After sign-in, use one shared workspace and the sequence: review the household case, calculate cash flow, save the assessment, then record a named officer review. Show the finding before save or review actions. Keep stress settings, repayment schedules and source details available through disclosure controls. Saved history shows the finding and review status; advisory review remains distinct from the lender’s credit decision.

## Persistence

Use one PostgreSQL database per environment for accounts, sessions, assessments, reviews and drafts, with Django models and migrations. Local development and integration tests use PostgreSQL too. Domain rules remain independent of Django. Per-case transaction locks serialize versions, drafts and officer decisions; database triggers reject changes to saved assessments, reviews and drafts.

The sign-in and workspace follow Kountwise’s shared palette, spacing, navigation and compact form layout. CSS and JavaScript URLs carry content versions so a new template cannot silently retain an old cached stylesheet.
