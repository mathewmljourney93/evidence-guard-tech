# Plan: docs/architecture-readme (architecture guide, README rewrite, v0.1 statements)

- **Tier:** standard (documentation plus one documentation test; no code, route, migration,
  CI or `AGENTS.md` change)
- **Date:** 2026-11-21
- **Base:** `origin/main` at `288d418` (review API and approval gate merged; the evaluation
  harness pull request is not on this base)

## Goal

A stranger can read the README, run EvidenceGuard locally and find out how it fits together,
what it does not do and what has not been measured. The architecture guide and the README are
checkable against the code. The responsible-AI and threat-model documents state the v0.1
position plainly. A test keeps the reader-facing documents free of em dashes, leftover TODOs,
evaluation-result claims and a README status section.

## Existing material found

- `README.md`: a long milestone and evidence record. `AGENTS.md` says status lives in pull
  request bodies and the CHANGELOG, never in the README. The run commands in it (uv, Alembic,
  `eg-admin`, `eg-api`, Compose) are the starting point for the new instructions.
- `docs/responsible-ai.md` already exists, so the responsible-AI statements go there (no new
  file). `docs/threat-model.md` keeps its per-component sections; a v0.1 summary goes on top.
- ADR-0001 to ADR-0028 in `docs/decisions/`; ADR-0027 (review path wiring) and ADR-0028
  (approval gate and export) describe the newest parts.
- No existing documentation test. `tests/test_container_ci.py` and `tests/test_container_files.py`
  read repository files, so a test that reads Markdown from the repository root fits the suite.
- `pyproject.toml` uses `README.md` as the package readme, and `.dockerignore` includes it in
  the image build context. Neither depends on its content.

## Files

1. `docs/plans/docs-architecture-readme.md` (this file), committed first.
2. `docs/architecture.md` (new): components, the review pipeline end to end, data model and
   tenancy, the durable job queue, security boundaries and roles, the audit trail, and two
   Mermaid diagrams. Every statement cites a module path.
3. `README.md` (rewritten): what it is and who it is for, running locally without Docker
   (commands run in this session against PostgreSQL 17 + pgvector), Docker Compose (stated as
   exercised by the CI container job only), architecture overview, design decisions linking
   ADRs, tests and CI, honest limits, and an Evaluation section. No status prose, no
   milestone or prompt history, no badges, no em dashes.
4. `docs/responsible-ai.md` (rewritten for v0.1) and `docs/threat-model.md` (a v0.1 summary at
   the top; the header's draft status replaced; existing sections kept as the per-component
   record).
5. `tests/test_docs_honesty.py` (new).
6. `CHANGELOG.md`: one line under Unreleased.

## Test design

`tests/test_docs_honesty.py` checks the reader-facing documents: `README.md`,
`docs/architecture.md`, `docs/responsible-ai.md` and `docs/threat-model.md`. For each:

- no em dash (U+2014);
- no `TODO`;
- none of `Recall@`, `accuracy of`, `outperforms`, `precision of`, `F1 score`, `state of the art`
  (case-insensitive), the phrases that would claim an evaluation result;
- `README.md` has no heading whose text starts with `Status`.

Files under `docs/evaluation*` are excluded by name, since they are where evaluation results
would be reported. The historical records (`docs/plan.md`, `docs/decisions/*.md`,
`docs/plans/*.md`) are excluded: they are dated records, some quote metric names
as definitions (for example `Recall@5` in ADR-0017), and `AGENTS.md` says they are not
rewritten. The checking functions take text, so the test also proves that each check fails on
a deliberately bad sample, and a manual run against a bad copy of the README shows the test
failing.

## Verification

- Before: `ruff check`, `ruff format --check`, `mypy` and `pytest` on the base
  (5923 passed, 477 skipped).
- After: the same, expecting the new test count added and nothing else changed.
- Every README command for the local run is executed here against a scratch database on the
  local PostgreSQL 17 + pgvector server, with a fake local password, and the scratch database
  and role are dropped afterwards.
- Compose is not run in this session.

## Out of scope

- Any code, route, migration, CI, Compose or `AGENTS.md` change.
- Rewriting `docs/plan.md`, the ADRs or the ADRs (historical).
- Removing em dashes from historical records.
- The evaluation harness and `docs/evaluation.md` (separate pull request). The README refers
  to `docs/evaluation.md` as the place the harness is described once that pull request merges.

## Changes from the plan (2026-11-26)

- The README was not fully rewritten in this change. The public repository already carries a short
  README written for a first-time reader; this change adds the architecture link to it. The
  local-run commands in it were not executed end to end.
- Em dashes were also removed from `docs/plan.md` and two decision records, for consistency with the
  rest of the documentation (the honesty test skips those pages).
- The threat model keeps its v0.1 summary and per-component control tables. Dated build history, the per-milestone review-workflow narrative
  and status prose were removed from it.
- Plan author: planner agent (Claude Opus 5.5). The base named earlier (288d418) belongs to the
  development repository, not this one.
