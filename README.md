# FarmCredit

FarmCredit is a prototype for officer-reviewed agricultural input
and credit advisories, using records supplied by cooperatives, SACCOs and
microfinance institutions. The current implementation converts a seasonal case
with supplier-financed inputs into deterministic cash flows; it is not a lending
system or a completed AI agent.

## Run the checks

With Python 3.10 or newer, from the repository root:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The tests require no external services, credentials or third-party packages.
They include two synthetic maize cases where changing only the receipt date
changes whether repayment can be funded on time.

To install the package in an isolated environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m unittest discover -s tests -v
```

Installation requires access to the Python package index for build tools.

## Structure and limits

- `src/farmcredit/domain/`: seasonal case inputs, dated KES calculations and validation.
- `src/farmcredit/application/`: conversion from a seasonal case to cash flows.
- `tests/`: deterministic calculation and boundary tests.
- [docs/workflow.md](docs/workflow.md): agreed scope, research, fixtures and next steps.

The calculator preserves earlier shortfalls and excludes late receipts from
repayment capacity. Same-day receipts and payments require clarification.
Case conversion calculates saleable harvest and a single supplier-financed
repayment. Other cash movements must already be normalised; a source ID alone
does not prove evidence is valid. Results are not credit approvals.

Django/HTMX screens, other financing arrangements, persistence, MCP tools, model execution,
external evidence and human approval enforcement are not implemented yet.
No field validation or agent evaluations have been completed. The eventual
competition entry will need those capabilities and its required submission
artifacts; the current test command is not an end-to-end application demo.

## Licence

Copyright (c) 2026 MathaiMarvin. Licensed under the
[GNU Affero General Public License version 3 only](LICENSE) (`AGPL-3.0-only`),
without warranty. Commercial use is permitted subject to its terms. Modified
versions supporting remote network interaction must offer their corresponding
source to those users, as required by section 13. Distribution obligations also
apply; consult the licence for the complete terms.
