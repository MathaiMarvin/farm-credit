# FarmCredit

FarmCredit is a prototype for officer-reviewed agricultural input
and credit advisories, using records supplied by cooperatives, SACCOs and
microfinance institutions. The current implementation provides a Django case
workspace that calculates seasonal cash flows with supplier-financed inputs.
It is not a lending system or a completed AI agent.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then from
the repository root (Python 3.10 or newer):

```sh
uv run --locked farmcredit
```

Open http://127.0.0.1:8000. Change the receipt date from 10 September 2027 to
15 October 2027 to inspect a repayment timing shortfall. Price can also be
changed. All data is synthetic; changes are not saved. No database or external
credentials are needed. The server binds to loopback and uses development
settings; authentication and production deployment are outside this step.

## Run the checks

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
uv run --locked farmcredit check
```

The first run creates `.venv` and installs from `uv.lock`; package downloads need
network access. `pyproject.toml` declares dependencies and tool settings;
`uv.lock` pins the resolved versions. Use `uv add` (or `uv add --dev`) for changes
and commit both files. There is no separate requirements file.
Tests cover the synthetic scenarios, calculation boundaries, form validation,
HTMX and regular submissions, and CSRF protection. CI tests the installed package
on Python 3.10 and 3.14, including packaged templates and static files.

## Development process

Create a short-lived `feat/…` or `fix/…` branch from `development`. Open a PR into
`development` with the change, its purpose, validation and remaining limits.
Review the diff and require passing CI before merging. Promote a finished,
verified milestone through a separate PR from `development` to `main`.
Do not push product changes directly to either shared branch. `main` is the
stable demonstration baseline. Keep workflow detail in `docs/workflow.md`.

## Structure and limits

- `src/farmcredit/domain/`: seasonal case inputs, dated KES calculations and validation.
- `src/farmcredit/application/`: conversion from a seasonal case to cash flows.
- `src/farmcredit/adapters/`: synthetic case records.
- `src/farmcredit/interfaces/web/`: forms, views, templates and static assets.
- `tests/`: deterministic calculation and boundary tests.
- [docs/workflow.md](docs/workflow.md): agreed scope, research, fixtures and next steps.

The calculator preserves earlier shortfalls and excludes late receipts from
repayment capacity. Same-day receipts and payments require clarification.
Case conversion calculates saleable harvest and a single supplier-financed
repayment. Other cash movements must already be normalised; a source ID alone
does not prove evidence is valid. Results are not credit approvals.

Every calculation input now has a source snapshot: value, unit, source, recording
date, observed/declared/assumed basis and synthetic status. Missing, conflicting
or mismatched sources prevent a result. Scenario edits are explicit unsaved
assumptions; source details retain the replaced demo value. This checks provenance
coverage, not truth, source freshness or whether unrecorded household debts exist.

Price-only, harvest-only and combined stress tests reuse the baseline calculator.
The editable 20% defaults are illustrative assumptions, not calibrated forecasts.
Retained food and losses stay fixed; impossible harvest scenarios show no result.
Baseline evidence remains unchanged.

Other financing arrangements, persistence, MCP tools, model execution,
external evidence and human approval enforcement are not implemented yet.
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
