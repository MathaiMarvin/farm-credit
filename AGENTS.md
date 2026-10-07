# Working agreements

## Scope and communication

- Work on one agreed feature at a time. Before implementation, briefly explain its behaviour, simplest approach, impact and completion checks.
- Keep updates, PR descriptions and final responses concise. Report outcomes, verification and material limits.
- Keep product decisions in `docs/workflow.md` and setup instructions in `README.md`. Add documentation only for a distinct, necessary purpose.
- Keep synthetic/fictional-data disclosures in README, not user-facing UI. Apply the web presentation helpers to source text, agent prose and trace displays; do not mutate stored provenance or calculation inputs. Preserve assumption/observation labels and credit-approval boundaries.
- Preserve user edits. Do not stage unrelated changes or restore deleted content without understanding why it changed.

## Architecture and behaviour

- Keep domain rules independent of Django, storage, MCP and model providers. Application code coordinates use cases; adapters and interfaces handle external concerns.
- Prefer small, explicit functions and typed data. Add abstractions only for demonstrated needs; avoid speculative layers and services.
- Use Decimal for money. Keep calculations and policy enforcement deterministic; models gather and explain evidence.
- Distinguish unknown values from zero, assumptions from observations, and synthetic data from real records. Never invent evidence or successful runs.
- Consequential actions require a named human approval enforced server-side. Calculation results are not loan approvals.
- Use Django templates and HTMX with the agreed Kountwise theme. Apply Apple HIG principles through clear navigation, feedback, keyboard access and accessible controls; verify behaviour rather than claim blanket compliance.

## Tools and verification

- Manage dependencies with `uv` and `pyproject.toml`; commit `uv.lock`. Do not maintain a parallel requirements file. Preserve AGPLv3 and third-party licence notices.
- Test meaningful behaviour and failure cases. For UI changes, check the complete browser flow, errors and a narrow viewport; disclose anything unverified.
- Before a code PR, run:

  ```sh
  uv run --locked ruff check .
  uv run --locked ruff format --check .
  uv run --locked farmcredit test tests -v 2 --noinput
  uv run --locked farmcredit check
  uv build
  ```

- Use PostgreSQL exclusively for development, integration tests and deployment. Django’s test runner owns the isolated test database.
- Documentation-only changes need a diff review, not new tests. CI remains required for merging.

## Git workflow

- Keep changes local for user review. Do not push, open or update a PR, or merge until the user explicitly gives the go-ahead for those changes.
- Branch `feat/…` or `fix/…` from `development`; open a focused PR back to `development`.
- Promote a completed, verified milestone through a separate PR from `development` to `main`.
- Never push product changes directly to shared branches, bypass required checks or force-push shared history.
- Review the diff, resolve conversations and verify CI before merging. Explain what changed, why, how it was checked and remaining limits in the PR.
- `AGENTS.md` guides behaviour; CI and GitHub branch protection enforce the automated checks and merge requirements.
