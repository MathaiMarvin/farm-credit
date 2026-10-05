# FarmCredit

FarmCredit is a competition prototype for officer-reviewed agricultural input
and credit advisories, using records supplied by cooperatives, SACCOs and
microfinance institutions. The current implementation is only the deterministic
cash-flow foundation; it is not a lending system or a completed AI agent.

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

- `src/farmcredit/domain/`: dated KES cash-flow calculations and validation.
- `tests/`: deterministic calculation and boundary tests.
- [docs/workflow.md](docs/workflow.md): agreed scope, research, fixtures and next steps.

The calculator preserves earlier shortfalls and excludes late receipts from
repayment capacity. Same-day receipts and payments require clarification.
Its inputs must already be normalised, verified cash movements; a source ID
alone does not prove evidence is valid. Results are not credit approvals.

Django/HTMX screens, case normalisation, persistence, MCP tools, model execution,
external evidence and human approval enforcement are not implemented yet.
No field validation or agent evaluations have been completed. The eventual
competition entry will need those capabilities and its required submission
artifacts; the current test command is not an end-to-end application demo.

## Licence

[MIT](LICENSE). Test records are synthetic. Research links are citations, not
redistributed datasets or claims of institutional partnerships.
