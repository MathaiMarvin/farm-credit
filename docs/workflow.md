# FarmCredit: agricultural credit-assessment workflow

Status: scope reconciled with the original design and competition brief on 6 October 2026. Calculations, versioned evidence, human draft review, PostgreSQL persistence, bounded internal runs and four local MCP tools are implemented. Application intake, application-bound evidence checks and synthetic institutional review are implemented. WFP/HDX and KAMIS market adapters and external-MCP weather evidence are implemented locally. Autonomous investigation has passed local real-model acceptance; the broader eight-task agent evaluation remains pending. Software tests do not establish agent capability or institutional fit.

FarmCredit helps an officer assess whether a farmer can service proposed agricultural credit. The intended agent investigates institution and farm records, retrieves relevant weather and market evidence, invokes deterministic calculations and prepares a sourced recommendation for human review. The lender retains the credit decision. This document is the scope and delivery map; implementation details belong in [architecture.md](architecture.md).

## Scope and people

- The current demonstration covers one fictional cooperative, a prebuilt synthetic maize household and officer-entered synthetic applications with seasonal or supplied instalment repayments. The calculator accepts explicit dated schedules; institution imports and irregular-schedule fixtures remain pending.
- The institution supplies financial records and proposed terms. Agricultural evidence comes from the farmer, institution or extension officer with its basis recorded. Confirm who reviews and approves the advisory with a partner. The household is the beneficiary.
- SACCOs, cooperatives and microfinance institutions are potential record providers and customers. Their systems, data availability and policies are not assumed to be interchangeable.
- Officer approval applies to the advisory only. It does not approve credit. The lender retains that decision.
- Do not send advice, issue a credit flag, originate a loan request, order inputs or disburse funds in this version.
- Defer dairy production models, other crop models, interest-schedule generation, institution onboarding and production integrations. An unsupported case receives an explicit scope explanation.

The proposed extension-office and cooperative relationship is a demo arrangement, not a claim of an existing partnership.

## Agreed delivery map

**Target journey:** save application → agent investigates evidence → calculate when supported → save sourced recommendation or evidence request → named human review.

Keep one maize input-credit workflow, one fictional institution and varied synthetic households. Support the existing seasonal and supplied monthly schedules. SACCOs, cooperatives and microfinance institutions are potential users of the same workflow; this demo does not establish fit for every lender.

Runs now start from an immutable saved application, including incomplete intake. A fixed internal sequence retrieves saved records, calculates when supported and saves an advisory or evidence request; model-selected investigation remains feature 5. Historical assessment-bound runs, calculations and review history remain supported.

Deliver the rows below in order, one feature at a time. Features 1–5 are implemented and verified locally; features 6–7 remain pending.

| Order / feature | Smallest useful behaviour | Completion evidence |
| --- | --- | --- |
| **1. Application before assessment — implemented locally** | One intake page for farmer/farm, location/season, requested financing, supplied schedule and available records. Save and reopen incomplete applications. Bind runs to an authorised immutable application version; keep retrieved evidence attached to that run without rewriting the application. | Two different synthetic applications stay isolated. Missing yield or schedule survives saving as unknown. Investigation can start with gaps and produce an evidence request without a successful calculation. Old assessments remain readable; edits invalidate subsequent review eligibility. |
| **2. Institution evidence and policy — implemented locally** | Retrieve synthetic yield history, repayments, savings, current obligations and explicitly supplied demo lender rules. Distinguish recorded facts, missing records, affordability and eligibility. | Arrears and missing history change the findings; savings are not automatically spendable cash. Supplied policy checks are reproducible and versioned. No invented acceptance thresholds or claims of validated credit scoring. |
| **3. Market evidence — implemented locally** | Retrieve one supported commodity/market price source. Preserve source, observation/retrieval dates, geography, unit and price type; retain the officer's assumption alongside comparable evidence. | Check access/licence first. Demonstrate a real retrieval plus stale, incompatible-unit and unavailable cases. A wholesale quote cannot silently replace a farm-gate assumption; a justified alternative scenario is separately labelled and reproducible. |
| **4. Weather evidence — implemented locally** | Retrieve one source appropriate to the farm location, season and assessment date. Record the signal and its coverage for the agent to investigate. | Check access/licence first. Demonstrate real retrieval, geographic/time mismatch and provider failure. No future information in historical evaluations, or numerical yield adjustment without a validated method. |
| **5. Autonomous investigation — implemented locally** | One open-source orchestrator and an open-weights model use our tools and at least one borrowed MCP server to investigate gaps, inspect responses and choose the next permitted action. | A full task completes through actual model-selected calls. Missing/conflicting records change the path; an outage exercises bounded recovery. All external/model calls have traceable outcomes, timeouts, usage and cost reporting. The model cannot replace arithmetic, policy or approval. |
| **6. Officer walkthrough and review** | Start assessment from the saved application. Show concise actual progress, evidence, financial findings, unresolved eligibility/risk questions and a recommendation for review. | Complete desktop, keyboard and narrow-screen flow, including failed/incomplete runs and stale drafts. Demonstrate named agricultural-officer sign-off on the advisory and the lender's separate decision responsibility; confirm the role arrangement with intended users. |
| **7. Agent evaluations and submission** | Run at least eight varied tasks, including held-out cases, with recorded pass/fail outcomes. Compare against a fixed workflow using the same tools and records. | Repeat runs and report variation, unsupported claims, tool choices, recovery, latency and cost. Preserve one unresolved failure with a proposed next step. Package the required repository, one-command setup, architecture, evaluations and unedited demo. |

Feature 1 delivery: `/applications/` saves and reopens officer-owned synthetic applications, with immutable versions and optimistic edit checks. Missing yield, schedule or source details remain unknown. Supplied seasonal and instalment schedules use the existing Decimal calculator. The fixed **Check saved evidence** action records its actual calls and results, then saves an advisory or a questions-only evidence request without requiring a successful calculation. Retrieved saved evidence stays attached to the run's immutable tool result; intake is not rewritten. Editing and saving a new version invalidates earlier review eligibility, including when input values are later restored. PostgreSQL triggers protect application versions, and existing assessment history remains readable. Software checks cover two isolated households, denied cross-officer access, concurrent saves, stale reviews, missing evidence and application-bound MCP. Browser checks cover errors, reopening, draft review, keyboard actions and a narrow viewport. These are software verification results, not agent evaluations.

Intake supports one fictional cooperative, maize and supplier financing. Each application belongs to its creating named officer; institution membership and sharing are deferred to institutional access work. Source metadata applies to the supplied intake worksheet; missing metadata triggers source requests. Available-record notes are retained but do not count as verified institutional evidence. Blank cash-record rows do not assert no obligations: complete calculation requires an explicit cash-coverage date through the supplied schedule. The fixed check uses labelled 20% price and harvest stress assumptions, not forecasts.

Feature 2 delivery: three prefilled synthetic household forms link explicitly to `DEMO-001`, `DEMO-002` or `DEMO-003`. Names never select institutional records. Their cash-flow assumptions are the same; the institutional files differ. Each new application-bound run freezes the selected file, its observation date, retrieval timestamp, content fingerprint and the supplied demo review policy in its immutable scope. `get_records` retrieves yield history, repayments, savings, current obligations and lender policy from that frozen snapshot. Calculations and drafts use the same records; intake remains unchanged.

The deliberately small `demo-cooperative-review` policy, version `v1`, is an illustrative fixture authored for the demonstration, not a policy supplied or validated by a real lender. Its rules are: request unavailable repayment history; flag recorded unresolved arrears for named officer review; reconcile known institutional obligations to dated household cash records before calculation. These are review requirements, not an approval threshold, credit score or automated eligibility decision. KES 12,000 in recorded savings, including KES 10,000 restricted, is shown separately and never added to opening cash. Historical yields remain supporting records rather than replacement harvest assumptions. Missing records remain unknown; only an explicit empty obligations file represents recorded zero obligations within that institution's coverage.

The complete file proceeds to calculation; the arrears file produces an officer-review finding and a question about unresolved repayment timing; the file without repayment history requests evidence. Potential duplicate or mismatched obligations require clarification instead of silent insertion or deduplication. The institution panel is separate from cash-flow affordability. A changed linked file requires a new application version. A changed demo policy invalidates active investigations and draft approval eligibility; prior snapshots remain readable. Tests cover frozen evidence, exact arrears arithmetic, missing records, restricted savings, reconciliation, policy versions, citations and MCP boundaries. These fixed-sequence checks are software demonstrations, not model-selected investigation or agent evaluations.

Keep this demonstration simple for judges: use the three household entry points and one visible review policy. A general policy editor, arbitrary thresholds and institution onboarding are deferred. The next work is actual autonomous tool selection; the agent remains the central demonstration objective.

Weather and market evidence are both in scope. At least one integration must use an MCP server we did not write; verify its suitability and document why it is reused before implementing that provider. The other may use a direct adapter. Market evidence uses direct WFP/HDX and KAMIS adapters; weather reuses the tested external Open-Meteo MCP. The selected model is Qwen3-235B-A22B-Instruct-2507 through OpenRouter, checked against the real acceptance tasks below.

Feature 3 delivery: one explicit Nakuru reference market and maize commodity use [WFP Kenya Food Prices via HDX](https://data.humdata.org/dataset/wfp-food-prices-for-kenya), through a direct, bounded HTTPS CSV adapter. Official HDX metadata was checked on 6 October 2026: the dataset is licensed [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/). Attribution and licence links accompany the evidence. KAMIS is additionally integrated through its public price search, with its unverified reuse licence explicitly labelled. The public download receives no household information, needs no API key, and has a 10-second socket timeout and 8 MiB response limit. The provider URL, commodity, market and price type are server-controlled, not model-supplied.

The live retrieval on 6 October 2026 returned Nakuru wholesale maize at KES 35.88/kg for April 2022 (source date 2022-04-15). This is a real historical observation, not current market validation. The adapter selects only actual, non-future wholesale maize observations for the explicit reference market; it does not substitute a newer retail quotation or another geography. Missing or conflicting observations, malformed responses and failed downloads remain unavailable. The source's monthly dates are not presented as daily offers. A 90-day freshness limit is an explicit demo convention, not a validated lender rule. KES/kg and explicitly sized 90 KG quotes can be compared by deterministic Decimal conversion; other units/currencies remain incompatible.

Each new application-bound run captures the result or failure, retrieval timestamp, source, licence, geography, price type, original unit and fingerprint in its immutable scope. `get_records` exposes `market_prices`; calculations and drafts retain that same evidence and the officer's original sale assumption. Opening or saving an application does not fetch prices. A new investigation refreshes evidence without altering prior drafts. The evidence panel requests a current buyer quote and clarification of grade, location and transport/selling costs. No market-derived sale scenario is justified by this historical wholesale observation, so no substitute price or margin is invented; existing labelled stress scenarios remain reproducible and separate. Market warnings do not prevent calculating the explicitly assumed baseline, and that baseline is not validation of its price. Tests exercise stale, incompatible, unavailable and changed evidence. These are software tests, not actual agent evaluations.

KAMIS extension: an optional, explicit Nakuru Wakulima reference retrieves a single bounded public search page for dry maize within the prior 90 days. County, market, commodity, date and wholesale type are checked against every response row, because the live endpoint did not consistently honour a market filter without county. Classification and grade remain attached; competing latest prices/grades require clarification rather than averaging. The live check on 6 October 2026 returned no matching Nakuru Wakulima quote. The no-data outcome is retained independently beside WFP. The public search/about pages and robots endpoint were checked; no explicit reuse licence was found, and no open-data licence or redistribution right is asserted. Retain attribution and verify terms before wider/commercial redistribution. Neither source silently replaces the other or the officer's assumption.

Weather provider decision: reuse the Apache-2.0 `open-meteo-mcp` 0.2.0 package (source project `fcto-demos/open_meteo_mcp`, PyPI metadata also references `isamauny/open_meteo_mcp`). Its inspected date-range tool exposes hourly Open-Meteo forecasts and the resolved city coordinates. It is run unchanged over stdio in a separately uv-locked MCP v1 environment; FarmCredit's MCP v2 environment is retained. This is an external MCP implementation, not our own wrapper masquerading as a borrowed server. Its response includes prose instructions: only the JSON between the documented weather-data markers is parsed as evidence; those instructions are never executed or forwarded as authority. Its city-level coordinate resolution requires explicit geographic validation and does not establish exact farm/grid location. Open-Meteo data are CC BY 4.0; the free API is for non-commercial use under its published limits. This local non-commercial demonstration needs no API key; commercial deployment requires revisiting provider access terms.

Feature 4 delivery: an explicitly selected Nakuru city reference requests the current review date through six days ahead from the external server's `get_weather_byDateTimeRange` tool. A real MCP discovery and lookup on 6 October 2026 returned 168 hourly forecast records, with resolved coordinates -0.30719, 36.07225. These are model forecasts, not observations or calibrated drought/yield indicators. The model-grid coordinates are not exposed by this upstream tool, and exact farm conditions remain unverified. The local location check requires coordinates within 0.1 degrees of the explicit Nakuru reference; this is a demo identity check, not proof of farm representativeness. Timestamps must cover exactly seven consecutive UTC days; nulls stay unknown, malformed/geographically mismatched results cannot become usable evidence, and incomplete periods produce no fabricated totals. Valid precipitation totals and hourly temperature maxima are calculated deterministically.

Each run freezes the external server package, tool and arguments, start/completion timestamps, filtered data, result/failure and fingerprint. The adapter has a 30-second MCP deadline and accepts at most a 256 KiB response envelope; no credentials or household financial data are supplied to the server. `get_records` exposes weather alongside independently captured KAMIS and WFP evidence; calculations and drafts reference the same snapshot without changing price or yield inputs. The sample 2027 growing season lies outside the live forecast horizon, which is an explicit finding requiring better seasonal evidence. Historical/future review dates cannot trigger a live forecast: appropriately archived forecast support remains out of scope. New runs refresh weather, while old drafts remain readable as snapshots. Software tests cover mismatched location/time, unknown values, unavailable providers and exact run binding; they do not constitute agent evaluations.

Feature 5 delivery: **Investigate with agent** runs a small
LangGraph loop using the open-weights Qwen3-235B-A22B-Instruct-2507 model through
OpenRouter. The trusted launcher binds the officer/application and opens our actual
MCP subprocess. The model chooses among the four existing tools; it cannot choose
identity, change the case, replace arithmetic or approve a draft. External evidence
is fetched on the first model-requested category and frozen in append-only per-run
records. The fixed check retains its original eager snapshots for comparison.

PostgreSQL retains model requests/responses, MCP operations, external snapshots and
failures. Costs and tokens are provider-reported; missing or unconfirmed usage stays
unknown. There are 10 model requests, 12 tool calls and 120 seconds per run, one
transient model retry, 35 seconds per model request, a 3,000-token output cap and a
128 KiB context cap. The loop stops after 60,000 reported tokens. Source instructions
have no authority; citation membership, current inputs/policy and financial results
are checked server-side. Claim support still requires officer review and evaluation.

Verification: 284 software tests passed, including scripted branching, outage,
limit, rejected-action, audit and actual own-MCP transport checks. Scripted responses
are software tests, not agent evaluations. Real browser verification covered saved
intake → model run → trace → draft → separate review using a synthetic named test
officer, plus a 390-pixel viewport without overflow. This is not intended-user feedback.

Actual model acceptance on 6 October 2026 used Qwen3-235B-A22B-Instruct-2507,
Apache-2.0 open weights, through OpenRouter (`qwen/qwen3-235b-a22b-2507`), with
prompt `investigation-v3`. The fixed run binding supplied no expected answer to the
model. Local raw traces and harnesses are preserved in `.local/agent-acceptance/`;
`summary.json` maps outcomes to their immutable run IDs.

| Actual task | Observed result | Model calls / latency / reported cost |
| --- | --- | --- |
| Complete file, WFP + KAMIS + borrowed weather MCP | Saved cited advisory; requested a current buyer quote and seasonal evidence. | 4 / 45.03 s / $0.00667782 |
| Missing repayment history + one injected pre-send connection outage | Recovered after one configured retry; inspected an additional record set and saved an evidence request for repayment history. | 6 / 31.13 s / unknown total |
| Conflicting supplied principal, charges and schedule | Saved questions only, identifying KES 22,000 scheduled versus KES 23,000 principal plus charges. | 4 / 21.11 s / $0.00336130 |

The outage was deliberately injected, not an observed provider incident; all returned
model responses were genuine. The failed attempt has unknown usage, so total cost
stays unknown. The full-task run used all four own-MCP tools and the unchanged
borrowed weather MCP, with authoritative calculations and separate human review.

Retained failed attempts: an unsupported provider parameter caused HTTP 404 before
tool use; the initial 30B model invented citations that the server rejected, missed
the material conflict question, and later violated the questions-only draft contract.
Those findings drove the provider correction, clearer instructions and selection of
the larger model. We do not count terminal `completed` status alone as semantic success.
Remaining limitations: the selected model still performed an unnecessary calculation
attempt after missing institutional history; the deterministic tool withheld a
complete result. Narrative support and labels still require officer review. No broad
reliability rate, institutional fit or production-data readiness is established.

The eight-task held-out/repeated evaluation and an unresolved failure report remain
feature 7. Hosted inference is for synthetic demo inputs; data residency and consent
for real households remain outside the implemented deployment.

**Recommendation contract:** show whether the supplied evidence supports servicing the proposed schedule, relevant policy checks and agricultural risks, citations, assumptions and unanswered questions. Distinguish “supported under stated assumptions”, “shortfall/terms need review” and “insufficient evidence”. Avoid an overall viability score or automated loan approval. Any alternative terms must come from explicit supported options and be recalculated.

**Scope discipline:** before coding each row, state its behaviour, simplest approach, impact and checks; after delivery, record its actual status here. New work must advance this journey or fix a demonstrated defect. Broader crops, portfolio dashboards, multi-agent systems, production lender connections, automated credit actions and extra provider catalogues stay deferred. Keep changes local until review and explicit push approval.

## Competition completion gate

Source: [official agriculture brief](https://agentic-africa-challenge.lovable.app/tracks/agriculture), checked 6 October 2026. Selected sub-theme: **Input & credit risk**. The brief places the advisory in an agricultural-office workflow; the proposed cooperative/extension-office relationship still needs user validation.

- Own MCP server with at least three distinct tools including a write action: implemented and bound to saved applications; historical assessment bindings remain supported.
- Borrowed weather MCP and LangGraph orchestration: implemented locally. A full actual open-weights model task passed the recorded feature 5 acceptance.
- Logged actions and named human approval before consequential actions: implemented tool, external and model traces; actual acceptance traces are preserved locally. Household delivery, orders and credit flags remain outside this build.
- Public OSI-licensed repository, one-command setup, approximately 300-word description, one-page `ARCHITECTURE.md`, `EVALS.md` with at least eight actual task results and an unresolved failure, and a public unedited demo under three minutes: complete in feature 7. Move the existing architecture guide to the required submission filename then; do not maintain two copies.
- New-work/build-window eligibility and intended-user feedback: verify before submission; do not claim interviews or agent runs that have not occurred.

Agentic depth carries 30 points and evaluation/reliability 15. Passing deterministic tests is necessary infrastructure evidence; it does not satisfy either agent evaluation requirement. Expected answers remain outside model-visible inputs, and test cases must not be curated solely to pass.

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
3. Save the application even when evidence is incomplete. Start investigation against its immutable version and the applicable policy version.
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

The proposed first agent prepares a sourced cash-flow advisory for one authorised case and immutable input version. The four application capabilities below are implemented internally. The adapter authorises officer-owned application versions and the historical demo case FC-001, rechecking named officer access on every call; institution membership remains pending, and broader model evaluation remains pending.

Read tools preserve exact values, source basis, synthetic labels and missing/conflicting evidence. `get_records` retrieves saved intake evidence and, for application-bound runs, the frozen synthetic institutional file and demo review policy. Unmatched files and missing repayment history are explicitly unavailable. `assess_cashflow` recomputes saved inputs under the supported policy and explicit stress assumptions. Its reproducible calculation ID does not represent a persisted run.

`save_draft` stores immutable, versioned advisory or evidence-request drafts in PostgreSQL. It validates current inputs, citation membership and a recomputed calculation reference, and attaches authoritative figures separately from unverified narrative. Exact retries return the original draft; changed payloads using the same key fail. Officers can open drafts from their saved assessment, inspect citations and calculations, then approve the exact draft or request changes with a reason. These immutable decisions are separate from assessment reviews. A newer draft, newer assessment, policy change or input revision makes the earlier decision historical; stale forms cannot approve. Evidence-request approval confirms a request for records, not a completed finding. Internal run tracking binds an officer to a saved application version or historical assessment and records each allowed tool call before execution, then its actual result or failure. Calls are serial, duplicate call IDs reuse the recorded outcome, and advisory draft saves require a calculation returned in that run. An application with incomplete intake or unresolved institutional checks may save a questions-only evidence request without a calculation call; the server verifies the bound gaps and attaches the authoritative not-calculated finding. A run completes only when its draft is saved; failures and exhausted limits end it as incomplete. Interrupted calls retain their running record without an invented outcome. Final outcomes and run bindings are protected in PostgreSQL. Fixed internal runs have no model usage. Autonomous runs add immutable model identity, requests, responses and provider-reported usage/cost, with unknown totals for missing outcomes. The four tools are exposed over local MCP stdio with a short-lived signed credential bound to the officer and run. Tool arguments cannot select identity or case, and no approval tool is exposed. Model execution and the limited real-task acceptance are complete locally.

| Tool | Input and result | Enforced boundary |
| --- | --- | --- |
| `get_case` | Bound case/version → household facts, repayment schedule, source references and known gaps. | Access only the case authorised for this run; no arbitrary customer lookup. |
| `get_records` | Requested evidence categories → available records or explicit unavailable/conflicting status. | Read-only, case-scoped retrieval; never manufacture missing records. |
| `assess_cashflow` | Bound input version and explicit stress assumptions → calculation ID, dated findings and evidence issues. | Server resolves inputs and runs domain validation; model cannot submit replacement totals or change loan terms. |
| `save_draft` | Bound case/version, calculation ID if available, stress assumptions, cited explanation, questions and idempotency key → immutable draft/version. | Validate reference ownership and current version; attach authoritative figures server-side. Repeated identical saves return the same draft; changed payload with the same key is rejected. |

These four application capabilities are exposed through our MCP server. The delivery map above extends them to application versions and weather/market evidence; at least one external task will use a borrowed MCP. WFP/HDX has been verified for historical Nakuru maize evidence; the external weather MCP has been verified for short-range city-reference forecasts, not whole-season farm predictions. External text is evidence, never an instruction to change policy or invoke approval.

Investigation behaviour (limited actual acceptance verified): the agent chooses which gaps to investigate and which permitted read tools are relevant. Complete records can proceed to calculation; a missing repayment schedule triggers a record request; conflicting records require clarification; a provider outage permits only configured retries or an explicitly allowed alternative. Unresolved required evidence produces an evidence-request draft. The application preserves the actual execution trace and returns an incomplete run if generation or saving fails.

Initial demo limits: at most 12 tool calls including retries, one retry per transient read failure, 120 seconds elapsed and 12,000 total model tokens per run. These are configurable engineering limits, not lending policy. Enforce them outside the model, record usage and preserve failures; tune against measured runs. No further model calls after exhaustion. The internal dispatcher currently enforces 12 tool calls and checks the 120-second deadline before and after each call; late transactional results are rolled back. Expired runs are reconciled when inspected. External-provider timeouts, transient-read retries and model-token limits must be implemented with their integrations.

Drafts contain evidence status, authoritative calculation findings, record citations, assumptions, limitations and questions for the officer. The application UI shows actual tool activity and the resulting draft from the fixed check. Approval is a separate authenticated officer action bound to the exact draft/input version; input changes make approval stale. The agent has no approval tool. The lender retains the credit decision.

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

Outstanding decisions: verify the seasonal calendar and package assumptions, choose one evidence source per need, define freshness rules and supported price conversion, and validate any intended real lender policy separately from the illustrative demo review sheet. Financial thresholds must remain labelled assumptions until validated with a relevant institution.

Implemented: seasonal and monthly cash-flow checks, immutable saved versions, authenticated officer review and PostgreSQL persistence. Local MCP tools now reuse bounded run tracking; application intake and application-bound investigation are implemented locally. Synthetic institution evidence and the versioned demo review policy are implemented locally. Market evidence is implemented locally. Weather evidence via an external MCP is also implemented locally. Autonomous model investigation passed local real-task acceptance. The next feature is the officer walkthrough and review. Validate the workflow with officers before claiming institutional fit.

Officer walkthrough (to be arranged by the project owner; no interviews completed):

1. Ask a credit officer and agricultural officer to describe one product using a blank form or redacted schedule, without personal customer records.
2. Confirm financing and collection methods, actual repayment dates/amounts, fees, grace periods, mandatory savings and treatment of existing deductions.
3. Identify available income/expense records, unknown outside debts, evidence freshness and which gaps force deferral.
4. Confirm eligibility/security checks, who owns the advisory and how it fits the existing approval process.
5. Replay a successful case and an early shortfall; ask what the current workspace misses. Record confirmed facts and unresolved questions here.

## Workspace interaction

Require sign-in before accessing any case, calculation, saved assessment or review. The public sign-in screen has no case data or workspace navigation. After sign-in, open Applications: save intake, check the saved evidence, inspect the resulting advisory or evidence request, then record a named officer review. The original Household case calculator and saved assessment history remain available. Show the finding before save or review actions. Keep stress settings, repayment schedules and source details available through disclosure controls. Saved history shows the finding and review status; advisory review remains distinct from the lender’s credit decision.

## Persistence

Use one PostgreSQL database per environment for accounts, sessions, applications, assessments, reviews, drafts and runs, with Django models and migrations. Local development and integration tests use PostgreSQL too. Domain rules remain independent of Django. Per-case transaction locks serialize versions, drafts and officer decisions; database triggers reject changes to application versions, saved assessments, reviews, drafts and draft reviews.

The sign-in and workspace follow Kountwise’s shared palette, spacing, navigation and compact form layout. CSS and JavaScript URLs carry content versions so a new template cannot silently retain an old cached stylesheet.
