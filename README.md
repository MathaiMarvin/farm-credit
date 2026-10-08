# FarmCredit

FarmCredit turns an incomplete agricultural credit application into an evidence-backed
advisory: an agent investigates records, identifies gaps, checks dated repayment cash
flow and explains what an officer should review next. A named officer can approve the
advisory or request changes. **The lender retains the loan decision.**

The current prototype investigates named agricultural enterprises and supports
single-harvest crop input-financing calculations, supplied institutional example
files, and officer-owned applications with seasonal or explicitly supplied instalment
schedules. Uzima Havillah is the proposed workflow context, not a validated partnership.
See [product scope and workflow](docs/workflow.md) and [architecture](ARCHITECTURE.md).

## Start the local demo

Prerequisites: Python 3.10+, [uv](https://docs.astral.sh/uv/getting-started/installation/),
and PostgreSQL 14+. The PostgreSQL role must be able to connect to the `postgres`
maintenance database and create the application database if it does not exist.

```sh
./scripts/demo
```

The launcher installs the locked dependencies and separate weather MCP runtime,
creates the database if absent, applies migrations, asks for a named officer account,
and starts <http://127.0.0.1:8000/applications/>. Existing accounts and records are
preserved. `./scripts/demo --no-server` performs setup only.

If `.env` exists, the launcher loads it. Set `OPENROUTER_API_KEY` there, or enter the
key at the hidden prompt; a prompted key is kept only in the process environment.
Leaving it blank keeps the fixed evidence check and calculator available. Model
investigations require funded OpenRouter access; a key spending limit is not an
account balance. Sending a request can incur charges. Never commit credentials.

The server is a **local development server**, not a production deployment. Applications
and sessions use PostgreSQL; a persistent local signing secret lives in ignored
`.local/demo-secret`. Set `FARMCREDIT_SECRET_KEY` to override it.

### Manual setup

```sh
createdb farmcredit
uv sync --locked
uv sync --project tools/weather-mcp --locked
uv run --locked farmcredit migrate
uv run --locked farmcredit createofficer your-username --name "Your Name"
uv run --locked --env-file .env farmcredit
```

Create the database and account once. The last command requires an existing `.env`;
omit `--env-file .env` if variables are already exported or no model connection is
needed. Plain `uv run farmcredit` does not load `.env` automatically. Restart the
server after changing its environment.

| Setting | Purpose |
| --- | --- |
| `PGDATABASE` | Application database; defaults to `farmcredit` |
| `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD` | PostgreSQL connection; omitted fields use libpq defaults |
| `OPENROUTER_API_KEY` | Hosted model access; never sent to the browser |
| `FARMCREDIT_SECRET_KEY` | Shared signing secret for web and local MCP processes |
| `FARMCREDIT_WEATHER_PYTHON` | Optional absolute path to the separate weather virtual environment's Python |

Keep the weather interpreter's virtual-environment path rather than resolving its
symlink. Database backups use standard PostgreSQL tooling such as `pg_dump`.

## Walk through a case

1. Sign in and select **Open a case with the agent** from Applications. The preview
   explains the household's request and your reviewing role. Opening the workspace
   saves the application; it does not call the model.
2. Choose a suggested question or type a request, then **Send to agent**. Suggestions
   only fill the composer. Follow the recorded action and returned evidence checks;
   expand **View activity** for details.
3. Review the saved finding, open questions and calculation. **Review finding and
   sources** opens the evidence and named officer review.
4. Approve the advisory or request changes. A change request requires a reason.
   The saved decision appears in the case. Neither action approves or declines a loan.
5. Use **Ask a follow-up** for another investigation. Follow-ups use the previous
   saved model response as context and recheck the saved application. To change
   facts, open **Application details** and save a new version first.

The three household entry points use the same cash-flow assumptions but different
linked institutional files: complete records, recorded arrears, and missing repayment
history. Missing evidence remains unknown. Editing a case or creating a newer draft
makes earlier drafts historical and blocks their approval.

**History → Compare with the fixed evidence check → Check saved evidence** runs a
fixed tool sequence without a model. It can still retrieve selected external evidence.
The guided repayment calculator is a separate deterministic
exploration; it does not demonstrate autonomous tool selection.

## Demonstration data and boundaries

Households, cooperative records, repayment histories and the review policy are
**synthetic fixtures**, not customer records or validated lender policy. Results are
computed from those inputs, not evidence of real lending outcomes. The interface
avoids repeated synthetic-data banners; assumption, observation and forecast labels
remain visible. Original provenance and model/tool traces remain stored unchanged;
presentation helpers apply neutral wording only when rendering them.

The model receives application records through hosted OpenRouter inference. This
prototype does not promise in-country processing and is not configured for real
household data. Applications belong to their creating officer; institution-wide
sharing, production lender integration, loan origination, disbursement, farmer
messaging and validated credit scoring are not implemented.

## Model execution and recovery

LangGraph coordinates `qwen/qwen3-235b-a22b-2507` through OpenRouter and FarmCredit's
scoped MCP tools. Only deterministic code calculates money, and no model tool can
approve an advisory or a loan. See [execution boundaries](ARCHITECTURE.md#execution-and-failure-handling).

Keep the page open while a run executes. Progress reads do not start more model work.
A follow-up is a new investigation and can incur further charges. Evidence retrieval
is frozen within each run; there is no cross-run response cache or background queue.

If updates are interrupted, reopen the case and inspect the recorded outcome before
retrying. A completed run requires a saved draft. Interrupted processes do not resume
automatically. Provider errors show a safe explanation; failed or interrupted calls
may still incur charges and can leave usage unknown. A specifically identified
transient in-flight credit reservation is retried once only when its numeric
`Retry-After` delay fits the remaining deadline. Permanent credit/key limits are not
retried. Avoid overlapping paid tests and demonstrations.

## External evidence and attribution

Selected references retrieve external evidence; no reference means no download.
Provider failures, stale observations and incompatible geography, time or units
remain explicit gaps. Quotes never overwrite the supplied sale-price assumption;
weather does not generate a numerical yield adjustment.

| Integration | Behaviour and attribution |
| --- | --- |
| WFP Kenya Food Prices via HDX | Bounded CSV retrieval from `data.humdata.org`; preserves market, month, unit and wholesale basis. [Dataset](https://data.humdata.org/dataset/wfp-food-prices-for-kenya), [CC BY 3.0 IGO](https://creativecommons.org/licenses/by/3.0/igo/). A historical quote is not a current buyer offer. |
| KAMIS | Bounded public search on `kamis.kilimo.go.ke`; market and commodity must match. Attribution: Kenya Agricultural Market Information System, Ministry of Agriculture. Reuse licence has not been established; do not assume unrestricted redistribution. |
| Open-Meteo | Uses unchanged Apache-2.0 `open-meteo-mcp==0.2.0` in `tools/weather-mcp`, isolated from the main MCP runtime. City/date requests go to `geocoding-api.open-meteo.com` and `api.open-meteo.com`, without household or loan values. [Weather attribution](https://open-meteo.com/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), [API terms](https://open-meteo.com/en/terms). |

A selected Kenyan town reference is resolved against Open-Meteo’s location service and checked against returned forecast coordinates. It is not an exact farm coordinate. Its short forecast
cannot establish conditions for the demonstration's 2027 growing season. Live forecasts
are refused for historical review dates. Network access is required for external
retrieval and hosted model calls; local software tests use controlled responses.

## Verification and contribution

```sh
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked farmcredit test tests -v 2 --noinput
uv run --locked farmcredit check
uv build
```

Django creates and destroys the isolated `test_farmcredit` PostgreSQL database; the
test role needs database-creation permission. CI checks installed packages on Python
3.10 and 3.14, migration consistency, lint, tests and packaging. Software tests do
not establish hosted-model reliability or institutional fit. UI changes additionally
need browser checks for the complete journey, errors, keyboard access and a narrow
viewport. Live model calls are deliberate, budgeted checks, not part of CI.

Manage dependencies with `uv` and commit `pyproject.toml` plus `uv.lock`. The weather
runtime has its own lockfile; no parallel requirements file is maintained.

Create `feat/…` or `fix/…` branches from `development`. Review and verify changes,
then use a PR into `development`; promote a verified milestone through a separate
PR from `development` to `main`. Do not push product changes directly to shared
branches or bypass required checks. [AGENTS.md](AGENTS.md) contains working agreements.

## Licence

Copyright (c) 2026 MathaiMarvin. [GNU Affero General Public License version 3 only](LICENSE)
(`AGPL-3.0-only`), without warranty. Retain its notices and corresponding-source obligations.
HTMX 2.0.11 is vendored under the Zero-Clause BSD licence, retained beside the script.
LangGraph is MIT-licensed; the [Qwen model weights](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507)
and borrowed weather MCP server use Apache-2.0. Third-party data terms remain separate.
