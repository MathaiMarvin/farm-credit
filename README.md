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

Open http://127.0.0.1:8000 and sign in. All case and assessment routes require
authentication. Change the receipt date from 10 September 2027 to 15 October
2027 to inspect a timing shortfall. Calculate, select **Save assessment**, then
review the saved finding. Use **Compare with current case** to inspect changes.
All records are synthetic; approval applies to the advisory, never a loan.
The named reviewer needs advisory-review permission, granted by `createofficer`.
A review must match the latest version and submitted inputs. Historical versions
and reviews remain immutable, including after later inputs change.

Accounts, sessions, assessments, reviews and drafts share one PostgreSQL database,
managed through Django migrations. Back it up with PostgreSQL tooling such as
`pg_dump`. This is still a single-case demo without institution-level access
separation. Browser edits must be submitted before the server sees a changed case.

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
The UI offers fixed demo schedules; importing lender records and generating
interest schedules remain future work.

Four internal capabilities are implemented: `get_case`, `get_records`,
`assess_cashflow` and `save_draft`. They bind to one authorised saved version,
recheck officer access, preserve evidence labels and calculate with Decimal.
Drafts are immutable, validate citations and current inputs, and attach
server-calculated figures. Exact retries reuse the original draft. Draft review
UI, institution access, MCP registration and model execution remain pending.

Other financing arrangements, MCP tools, model execution,
external evidence and production institution access controls are not implemented yet.
No field validation or agent evaluations have been completed. The eventual
competition entry will need those capabilities and its required submission
artifacts; this screen demonstrates calculations, not an agent run.

HTMX 2.0.11 is vendored from its npm release under the Zero-Clause BSD licence;
its licence is preserved beside the script in `static/farmcredit/vendor/`.
The remaining interface code is original. Colours follow the supplied Kountwise
reference; typography uses the system font when Inter is not available.

## Licence

Copyright (c) 2026 MathaiMarvin. Licensed under the
[GNU Affero General Public License version 3 only](LICENSE) (`AGPL-3.0-only`),
without warranty. Commercial use is permitted subject to its terms. Modified
versions supporting remote network interaction must offer their corresponding
source to those users, as required by section 13. Distribution obligations also
apply; consult the licence for the complete terms.
