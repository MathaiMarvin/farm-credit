# FarmCredit

FarmCredit is a prototype for officer-reviewed agricultural input
and credit advisories, using records supplied by cooperatives, SACCOs and
microfinance institutions. The current implementation provides a Django case
workspace that calculates seasonal cash flows with supplier-financed inputs.
It is not a lending system or a completed AI agent.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and have
PostgreSQL 14 or newer running. FarmCredit uses PostgreSQL in every environment.
For a local PostgreSQL installation using your system account:

```sh
createdb farmcredit
uv run --locked farmcredit migrate
uv run --locked farmcredit createofficer your-username --name "Your Name"
uv run --locked farmcredit
```

Create the database and officer account once. For TCP or hosted PostgreSQL, set
`PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` in your environment.
The default database is `farmcredit`; omitted connection fields use libpq’s
local defaults. Set a persistent `FARMCREDIT_SECRET_KEY` to retain sessions across
restarts. The development server binds to loopback; deployment configuration is
still required before hosting.

Open http://127.0.0.1:8000/applications/ and sign in. Select **New application**
to enter a synthetic household, farm, location, season, supplier-financing request,
supplied schedule and available records. Blank numbers remain unknown; enter zero
only when confirmed. Save incomplete applications and reopen their immutable versions.
Applications are accessible only to the named officer who created them; institution
membership and shared officer access are not implemented.

For a short demonstration, use the three **Try a synthetic household** links on
Applications. They prefill a reviewable form with the same cash-flow assumptions
and explicitly link different institutional files: complete records, recorded
arrears, or missing repayment history. Saving the form creates your own application.
The **Synthetic institution file** field controls this link; names never guess it.

Select **Check saved evidence** to run a fixed internal sequence against that saved
version. It freezes and retrieves the selected synthetic institutional file and demo policy,
checks the records, calculates when supported and saves an advisory or evidence request. The page links to the actual tool trace and human
draft review. This does not run a model; selected references retrieve WFP/HDX, KAMIS and Open-Meteo evidence. Institution records and the policy are frozen in the run binding and returned in
its immutable tool results; they do not rewrite intake.
The institutional findings are separate from cash-flow affordability. The explicitly
illustrative `demo-cooperative-review` v1 requests missing repayment history, flags
unresolved arrears and reconciles existing obligations. It supplies no lending score
or acceptance threshold. Savings remain outside available cash, and historical yields
do not replace expected harvest assumptions. Missing evidence produces a request;
unmatched or possibly duplicated obligations require clarification.
Editing and saving a new application version makes earlier drafts historical and
prevents their approval. Changing the supplied demo policy also blocks stale review. Apply migrations when updating an existing installation.

The original calculation demonstration remains under **Household case**. All case and assessment routes require
authentication. Change the receipt date from 10 September 2027 to 15 October
2027 to inspect a timing shortfall. Calculate, select **Save assessment**, then
review the saved finding. Use **Compare with current case** to inspect changes.
All records are synthetic; approval applies to the advisory, never a loan.
The named reviewer needs advisory-review permission, granted by `createofficer`.
A review must match the latest version and submitted inputs. Historical versions
and reviews remain immutable, including after later inputs change.

Accounts, sessions, applications, assessments, reviews, drafts and runs share one PostgreSQL database,
managed through Django migrations. Back it up with PostgreSQL tooling such as
`pg_dump`. This is a synthetic demo with officer-owned applications, without institution-level
access sharing. Browser edits must be submitted before the server sees a changed case.

## Autonomous investigation setup

The local implementation uses MIT-licensed LangGraph and the Apache-2.0
[Qwen3-235B-A22B-Instruct-2507 open weights](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507),
served through OpenRouter. Real synthetic acceptance runs completed the full evidence task, missing-history
handling with a controlled outage, and conflicting-term clarification. These limited
checks do not replace the separate eight-task evaluation.

Apply migrations and install the weather MCP environment described below. Configure
`OPENROUTER_API_KEY` in the environment of the process starting FarmCredit, then
restart the server. Do not commit the key. A `.env` file is not automatically loaded.
For local setup, create a key at [OpenRouter API keys](https://openrouter.ai/settings/keys)
and place `OPENROUTER_API_KEY=your_actual_key` in the repository-root `.env`
(already excluded from Git). Then start from the same terminal:

```sh
chmod 600 .env
set -a
source .env
set +a
uv run --locked farmcredit migrate
uv run --locked farmcredit
```

The fixed model ID is `qwen/qwen3-235b-a22b-2507`; outbound HTTPS to
`openrouter.ai` is required. Set an account/key spending limit in OpenRouter.

Save a synthetic application and select **Investigate with agent**. Application
records returned by tools are sent to the hosted model; this demo does not promise
in-country processing and is not configured for real household data. The agent
selects tools over our actual MCP connection. Requested external categories retrieve
and freeze their selected provider evidence once per run, including the borrowed
weather MCP. Only the existing deterministic tools calculate and save drafts.
**Check saved evidence** retains the fixed comparison workflow without model access.

Runs allow 120 seconds, 12 tool calls, at most 10 model requests and one retry for
transient model connection, rate-limit or server failures. Each model call has at
most 35 seconds and 3,000 output tokens; context is capped at 128 KiB and the loop
stops after 60,000 reported tokens. These are execution limits, not a monetary cap.
An unavailable external snapshot stays frozen: the agent can inspect a linked
alternative or request better records, rather than repeatedly download it.

The run page exposes model requests, public responses, MCP selections, returned
results, failures and provider-reported token/cost values. Secrets and private
reasoning are excluded. Missing usage, failed or interrupted requests keep total
usage/cost unknown; a timeout may still incur provider charges. A saved draft is
required for a completed run. Approval remains a separate named-officer action.
An interrupted process leaves its durable requests visible; there is no background
resume worker. Start a new run to retry an incomplete investigation.

Feature 5 acceptance is recorded in `docs/workflow.md`, with local raw traces in
`.local/agent-acceptance/`. The separate eight-task evaluation, repeated-run reliability
and production data residency remain outstanding. The smaller 30B candidate produced
rejected citations and a draft-contract failure; those failed traces are retained.

## Market evidence demo

Open `/applications/` and choose a synthetic household. Its form selects the
Nakuru market reference; save it, then use **Check saved evidence**. The investigation
retrieves WFP's Kenya food-price CSV through HDX, with no API key. Outbound HTTPS to
`data.humdata.org` is required. No household data is sent. With no market selected,
no download is attempted. Retrieval failures remain visible; a new investigation retries.

The draft retains the officer's assumed sale price and displays the source price,
month, unit, geography, wholesale basis, retrieval time and attribution. The verified
Nakuru series currently ends in April 2022: expect a historical-price warning and a
request for a current buyer quote, not a current-price claim. The 90-day freshness
limit is a demo convention. Real external observations are labelled separately from
synthetic household records. Data attribution: WFP via HDX,
[CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/),
[Kenya Food Prices](https://data.humdata.org/dataset/wfp-food-prices-for-kenya).

The demo form also selects **Nakuru Wakulima — KAMIS dry maize**. Its adapter
uses one public search on `kamis.kilimo.go.ke`, checks each returned market and
commodity, and preserves its quote or unavailable result independently from WFP.
The verified search returned no matching quote; no other market or retail price
is substituted. Attribution: Kenya Agricultural Market Information System,
Ministry of Agriculture. No explicit reuse licence was found on the checked pages;
verify terms before wider/commercial redistribution.

## Weather MCP setup

Install the separate, pinned third-party server from the repository root:

```sh
uv sync --project tools/weather-mcp --locked
```

FarmCredit launches `tools/weather-mcp/.venv/bin/python -m open_meteo_mcp --mode stdio`
when an investigation has a selected weather reference. The external server uses
MCP v1; its separate `pyproject.toml` and `uv.lock` keep that dependency isolated
from FarmCredit's MCP v2. No copied or modified provider server is maintained here.
For an installed package or a different working directory, set
`FARMCREDIT_WEATHER_PYTHON` to that environment's absolute Python path, preserving
the virtual-environment path rather than resolving its interpreter symlink.

The demo selects a **Nakuru city reference**, not an exact farm coordinate. Its
seven-day hourly forecast goes through the external server's
`get_weather_byDateTimeRange` tool. Outbound HTTPS to
`geocoding-api.open-meteo.com` and `api.open-meteo.com` is required. Only the
reference city and dates are supplied; household records and loan values are not.
A 30-second overall MCP deadline and 256 KiB accepted data-envelope limit apply.
Missing setup or a provider failure produces an explicit evidence gap.

The forecast does not cover the demo's 2027 growing season. The draft preserves
that limitation, forecast totals, source and retrieval time, and keeps harvest
assumptions unchanged. Starting a new investigation refreshes evidence; older
drafts retain their snapshots. Live forecasts are refused for historical review
dates rather than leaking present-day information into past evaluations.

External server: [`open-meteo-mcp` 0.2.0](https://pypi.org/project/open-meteo-mcp/),
Apache-2.0 (licence is retained in the installed package). Weather data:
[Open-Meteo](https://open-meteo.com/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The [free API terms](https://open-meteo.com/en/terms) permit non-commercial use
within published rate limits; revisit access terms before commercial deployment.

## Run the checks

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked farmcredit test tests -v 2 --noinput
uv run --locked farmcredit check
```

The first run creates `.venv` and installs from `uv.lock`; package downloads need
network access. `pyproject.toml` declares dependencies and tool settings;
`uv.lock` pins the resolved versions. Use `uv add` (or `uv add --dev`) for changes
and commit both files. There is no separate requirements file.
Django’s test runner creates and destroys an isolated `test_farmcredit` database;
the development/test database role needs permission to create databases. CI uses
a PostgreSQL service. Tests cover the synthetic scenarios, calculation boundaries, form validation,
HTMX and regular submissions, and CSRF protection. CI tests the installed package
on Python 3.10 and 3.14, including packaged templates and static files.

## Development process

Keep changes local until the user has reviewed them and approved pushing.
Create a short-lived `feat/…` or `fix/…` branch from `development`. After approval, open a PR into
`development` with the change, its purpose, validation and remaining limits.
Review the diff and require passing CI before merging. Promote a finished,
verified milestone through a separate PR from `development` to `main`.
Do not push product changes directly to either shared branch. `main` is the
stable demonstration baseline. Keep workflow detail in `docs/workflow.md`.

## Structure and limits

- [docs/architecture.md](docs/architecture.md): implemented layers, data flow and safeguards.
- `src/farmcredit/domain/`: seasonal case inputs, dated KES calculations and validation.
- `src/farmcredit/application/`: conversion from a seasonal case to cash flows.
- `src/farmcredit/adapters/`: synthetic records, PostgreSQL repositories and Django persistence models/migrations.
- `src/farmcredit/interfaces/web/`: forms, views, templates and static assets.
- `tests/`: deterministic calculation and boundary tests.
- [docs/workflow.md](docs/workflow.md): agreed scope, research, fixtures and next steps.

The calculator preserves earlier shortfalls and excludes late receipts from
repayment capacity. Same-day receipts and payments require clarification.
Case conversion calculates saleable harvest and a single supplier-financed
repayment or a supplied instalment schedule. Other cash movements must already be normalised; a source ID alone
does not prove evidence is valid. Results are not credit approvals.

Every calculation input now has a source snapshot: value, unit, source, recording
date, observed/declared/assumed basis and synthetic status. Missing, conflicting
or mismatched sources prevent a result. Scenario edits remain explicit assumptions
when saved; source details retain the replaced demo value. This checks provenance
coverage, not truth, source freshness or whether unrecorded household debts exist.

Price-only, harvest-only and combined stress tests reuse the baseline calculator.
The editable 20% defaults are illustrative assumptions, not calibrated forecasts.
Retained food and losses stay fixed; impossible harvest scenarios show no result.
Baseline evidence remains unchanged.

Choose **Monthly instalments** to inspect six explicitly supplied synthetic
payments. The same calculator reports every due-date balance and retains earlier
funding gaps even when harvest leaves a final surplus. Schedule amounts must
reconcile to principal plus stated charges, with matching source evidence and
explicit household cash-flow coverage through the final instalment. Coverage is
a recorded assertion, not independent proof that all household obligations exist
in the data. Negative balances represent accumulated unmet obligations.
The original calculator offers fixed demo schedules. Application intake accepts explicit
dated payments; importing lender records and generating interest remain future work.

Four internal capabilities are implemented: `get_case`, `get_records`,
`assess_cashflow` and `save_draft`. They bind to one authorised saved version,
recheck officer access, preserve evidence labels and calculate with Decimal.
Drafts are immutable, validate citations and current inputs, and attach
server-calculated figures. Exact retries reuse the original draft. Saved assessment
pages link to draft review: a named officer can inspect citations,
approve that exact draft or request changes. New drafts and changed inputs make
earlier decisions historical. Application drafts can be created through the fixed evidence check; institution
access sharing remains pending; model execution is available through **Investigate with agent** once configured.

Internal `start_run`, `invoke_tool` and `run_details` operations persist actual tool
activity for one officer and saved case. Runs enforce call/deadline limits, preserve
failures and reuse identical call retries. Advisory drafts reference a calculation from their run. An application with intake gaps or unresolved institutional checks can
save a questions-only evidence request without a calculation call. The application
page exposes the recorded tool activity. The fixed check starts no model; the agent action adds model and MCP traces.

Other financing arrangements and production institution access controls are not implemented yet.
No field validation or agent evaluations have been completed. The eventual
competition entry will need those capabilities and its required submission
artifacts; the fixed calculator remains a calculation demonstration.

HTMX 2.0.11 is vendored from its npm release under the Zero-Clause BSD licence;
its licence is preserved beside the script in `static/farmcredit/vendor/`.
The remaining interface code is original. Colours follow the supplied Kountwise
reference; typography uses the system font when Inter is not available.

## MCP tools (local stdio)

`uv run --locked farmcredit-mcp` exposes `get_case`, `get_records`,
`assess_cashflow` and `save_draft` using the official MCP Python SDK.
`get_records` additionally accepts `yield_history`, `savings`, `current_obligations`
and `lender_policy`; `repayment_history` now reads the bound synthetic file when
available. No tool argument can change the linked household or policy.

A trusted launcher first calls `start_run(officer_id=..., application_id=...)`,
using an immutable saved application version ID. Historical assessment-bound runs
remain supported with `assessment_id` instead. The launcher
then calls `issue_run_token(run_id=..., officer_id=...)` from
`farmcredit.interfaces.mcp.server`. Identity must come from the authenticated
session. Pass the returned token as `FARMCREDIT_MCP_TOKEN` in the child process
environment, alongside the same `FARMCREDIT_SECRET_KEY` and PostgreSQL settings
as the issuing process. Keep tokens and secrets out of prompts, arguments and logs.

The signed credential expires after 120 seconds; the existing run deadline and
12-call limit also apply. Each call requires a UUID `operation_id`; reuse it only
for an identical retry. Case and officer IDs are never tool arguments. A saved
draft ends the run and still needs human review. This is a trusted local transport,
not a public HTTP service. Tests exercise a real SDK client and stdio subprocess
against Django's isolated PostgreSQL database. The web evidence-check trigger uses the same dispatcher directly. No model launcher
is connected yet.

## Licence

Copyright (c) 2026 MathaiMarvin. Licensed under the
[GNU Affero General Public License version 3 only](LICENSE) (`AGPL-3.0-only`),
without warranty. Commercial use is permitted subject to its terms. Modified
versions supporting remote network interaction must offer their corresponding
source to those users, as required by section 13. Distribution obligations also
apply; consult the licence for the complete terms.
