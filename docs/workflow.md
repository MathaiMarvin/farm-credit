# Seasonal maize input credit workflow

Status: proposed implementation baseline, 5 October 2026. The product scope and Django templates plus HTMX are agreed; the detailed rules below are engineering proposals pending field validation. No agent runs or institutional validation have been performed.

FarmCredit helps a named agricultural extension officer review a household's proposed maize input package and associated credit terms. It combines institution-provided records with external evidence to produce a sourced draft advisory. This specification defines the first workflow and its limits before application scaffolding.

## Scope and people

- Demonstrate one fictional cooperative, one synthetic household case at a time, one maize season and one proposed repayment after harvest.
- The cooperative supplies farm and financial records. An extension officer checks the case and reviews the advisory. The household is the beneficiary.
- SACCOs, cooperatives and microfinance institutions are potential record providers and customers. Their systems, data availability and policies are not assumed to be interchangeable.
- Officer approval applies to the advisory only. It does not approve credit. The lender retains that decision.
- Do not send advice, issue a credit flag, originate a loan request, order inputs or disburse funds in this version.
- Defer dairy, other crop models, instalment loan assessment, institution onboarding and production integrations. An unsupported case receives an explicit scope explanation.

The proposed extension-office and cooperative relationship is a demo arrangement, not a claim of an existing partnership.

## Evidence behind the design

| Documented practice | Proposed design consequence |
| --- | --- |
| [Fariji SACCO](https://farijisacco.co.ke/loans) describes milk and agricultural advances aligned with milk or harvest proceeds and asks for cooperative or farm income records. | Record repayment dates and evidence of receipts; do not infer affordability from annual revenue. |
| [Equity's Micro Agribusiness Loan](https://equitygroupholdings.com/ke/borrow/agri-business/micro-agribusiness-loan/) describes repayment aligned with agricultural income cycles. | Compare receipt dates with obligations. This is supporting evidence from a bank, not validation of microfinance practices. |
| [FSD Kenya's 2022 annual report](https://www.fsdkenya.org/wp-content/uploads/2023/05/2022-FSD-Kenya-public-annual-report.pdf) documents a dairy pilot supplying fodder through cooperative check-off systems. | Model existing deductions explicitly. This historical dairy example motivates a question for maize partners; it does not establish universal maize practice. |
| [KAMIS](https://kamis.kilimo.go.ke/) distinguishes market, commodity, wholesale and retail quotations. | Preserve price type, unit, location and observation date; a quotation is not a guaranteed future farm-gate price. |
| [Alliance research on Kenyan index insurance](https://alliancebioversityciat.org/projects/innovation-africa-climate-risk-insurance) identifies basis risk and unreliable loss assessment among challenges. | Do not infer farm yield loss or guaranteed insurance proceeds from weather observations alone. |

These sources were reviewed on 5 October 2026. They support design questions, not a validated underwriting policy. We have not yet verified live provider APIs, data licences or a borrowed MCP server.

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
| Proposed credit | Principal, cash versus supplier financing, disbursement date, deductions or fees, total amount due and due date |
| Household cash | Available opening cash at the assessment start, dated essential cash needs, other income included only with an explicit evidence basis |
| Existing obligations | Payments due within the assessment period, existing produce deductions, arrears status and source coverage |
| Evidence | Source record ID, provider, observation or effective date, retrieval time, units, geography and whether observed, declared or assumed |

If exact household needs or outstanding obligations are unknown, record the gap and ask for confirmation. Do not assume institutional records cover debts held elsewhere. Do not require historical records to exist before recording a new farmer; explain when their absence prevents a supported assessment.

## Calculation contract

Use deterministic code for all arithmetic. The model cannot supply replacement totals or invent policy thresholds.

1. Saleable quantity = expected harvest minus retained quantity minus expected losses. All terms must use compatible units and refer to distinct quantities.
2. Expected sales receipts = saleable quantity times the stated assumed sale price. Selling costs are separate dated outflows unless the source explicitly supplies net receipts.
3. Construct dated cash inflows and outflows from the assessment start through the proposed repayment date. Include production costs, household cash needs and existing obligations within this window.
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

The agent can choose relevant read tools, investigate gaps, compare evidence, call the calculation tool and save a draft. Tool choice can vary by case. Financial validation, supported-scope checks and approval rules remain enforced in code.

Use bounded retries and a configured run budget. On exhaustion, preserve the trace and explain what remains unresolved. Saving a draft must be safe to retry without creating duplicate advisories.

Log tool names, arguments, results or errors and timestamps. Link factual claims to supporting record IDs. Log model and policy versions, token usage where available, elapsed time and measured or explicitly estimated cost. Expose decision summaries and tool evidence, not hidden model reasoning.

## Evaluation cases

These are planned synthetic tests inspired by real operating concerns. They are not claims about named farmers or completed runs. The first two calculation fixtures are specified below; remaining fixtures will be defined as their behaviour is implemented.

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
| Unsupported instalment schedule | Return the scope limit instead of treating it as a harvest balloon payment |
| Cash versus supplier financing | Equivalent economic inputs do not cause duplicated principal or fictitious cash |
| Input change after draft | Mark the prior assessment stale and reject approval of it |
| Repeated draft save | Preserve one logical draft for the same operation |
| Instruction embedded in retrieved evidence | Treat it as source data; it cannot change policy or invoke approval |

Keep evaluation answers separate from agent-visible records. Reserve unseen cases, repeat agent runs and report failures and run-to-run variation. Test arithmetic properties independently: reducing price cannot increase cash receipts when other inputs remain fixed. Officer approval must be enforced server-side.

## First two calculation fixtures

Both fixtures use the same synthetic two-acre maize household and change only the sale receipt date. Dates and amounts are test assumptions, not verified Kenyan crop calendars, market quotations or lending terms. They exercise calculation behaviour, not the complete agent or external evidence pipeline.

| Shared input | Test value |
| --- | --- |
| Opening available cash on 1 April 2027 | KSh 40,000; excludes restricted savings and loan proceeds |
| Inputs supplied on 2 April | KSh 20,000 paid directly by the lender to the supplier; no household cash movement |
| Other production cash costs | KSh 6,000 on 10 April, KSh 6,000 on 10 June and KSh 3,000 on 1 September |
| Household cash needs | KSh 2,500 on the 25th of each month, April through September; excludes food retained from this harvest |
| Existing debt repayment | KSh 5,000 on 15 August |
| Harvest on 1 September | 2,000 kg gross; retain 400 kg; lose 100 kg; sell 1,500 kg |
| Assumed sale price | KSh 40/kg before selling costs; expected receipt KSh 60,000 |
| Transport and selling costs | KSh 3,000 paid on 2 September, independently of receipt date |
| Proposed repayment on 30 September | KSh 22,000, comprising KSh 20,000 principal and KSh 2,000 total financing charges; no additional fees |
| Other cash flows through 30 September | Explicitly zero in these fixtures; never inferred from absent records |

Expected cash before sale receipts or proposed repayment is `40,000 − 15,000 − 15,000 − 5,000 − 3,000 = KSh 2,000`. The financed inputs are recorded separately, not deducted again. These expectations belong to the evaluator, not the agent's case inputs.

| Expected result | A: receipt on 10 September | B: receipt on 15 October |
| --- | --- | --- |
| Receipts available by repayment date | KSh 60,000 | KSh 0 |
| Cash immediately before proposed repayment | KSh 62,000 | KSh 2,000 |
| Cash after all obligations due on 30 September | KSh 40,000 | Projected deficit of KSh 20,000 |
| Earlier cash shortfall | None | None |
| Coverage, before repayment cash ÷ KSh 22,000 | 2.82× | 0.09× |
| Calculation finding | No shortfall under stated assumptions | Baseline shortfall caused by receipt timing |

Use exact decimal calculations and round displayed ratios to two decimal places using half-up rounding. Case B's negative balance represents unmet obligations, not an available overdraft or an executed payment. The expected October receipt remains visible as future evidence but cannot fund September repayment. Do not claim an October closing balance without modelling October obligations.

Case A must not become a loan approval or a claim that stress scenarios pass. Case B must identify the date and amount of the shortfall, without changing terms or moving the receipt date to make the case pass. Both outputs remain drafts for officer review. Missing or conflicting source evidence can still prevent either fixture from becoming a complete advisory.

## Architecture consequences

- Domain: quantities, dated cash flows, deterministic validation and calculations.
- Application: start assessment, collect evidence, save draft and review exact versions.
- Adapters: synthetic records first; later institution records, weather, market and model providers.
- Interfaces: Django templates plus HTMX for the officer, and MCP tools for the agent.

One common case contract accepts records from different sources without building separate SACCO, cooperative and microfinance applications. The first agent implementation needs an approved open-source orchestrator, an open-weights model run, our MCP server with at least three distinct tools including draft persistence, and a genuinely borrowed MCP server. Select those against a working data task, not a tool-count target.

## Field validation and next implementation gate

Ask an extension officer and an agricultural credit or cooperative officer to walk through one anonymised example: which records exist, when money arrives, which deductions are missed, which facts force deferral and what makes an advisory useful. Do not claim interviews occurred until they do; do not obtain personal customer records for the demo.

Outstanding decisions: verify the seasonal calendar and package assumptions, choose one evidence source per need, define freshness rules and supported price conversion, and establish explicit demo policy settings. Financial thresholds must remain labelled assumptions until validated with a relevant institution.

Implemented foundation: `src/farmcredit/domain/cashflow.py` calculates dated KES cash balances for one repayment, retaining future receipts and earlier deficits. It rejects duplicate source IDs, pre-opening movements, invalid amounts and ambiguous same-day receipt/payment ordering. That last rule is deliberately conservative until intraday ordering is supported. It accepts normalised cash movements; input-package normalisation, evidence validation, harvest calculations and the agent remain unimplemented.

Run checks from the repository root with Python 3.10 or newer: `PYTHONPATH=src python3 -m unittest discover -s tests -v`. The calculation has no third-party runtime dependencies. CI runs the same tests. Django and HTMX remain the agreed interface stack and will be added when the first interface is implemented.

Next: define the application boundary that turns a validated case into these cash movements. Keep production integrations and extra product features out of this step. Maintain this document as the shared workflow specification; add separate documentation only when its purpose requires it.

Competition reference: [Agriculture and Food Security track](https://agentic-africa-challenge.lovable.app/tracks/agriculture). The brief requires an officer-reviewed sourced advisory, tool traces, open-source delivery and honest evaluations. This document does not replace verification of final submission rules and dates.

## Workspace interaction

Use one shared workspace with visible officer sign-in and the sequence: review the household case, calculate cash flow, save the assessment, then record a named officer review. Show the finding before save or review actions. Keep stress settings, repayment schedules and source details available through disclosure controls. Saved history shows the finding and review status; advisory review remains distinct from the lender’s credit decision.
