# Changelog

Short record of merged changes, newest first. Details live in each pull request.

## Unreleased

- `eg-eval` evaluation harness (ADR-0029): a contract suite in CI that uses a scripted fake provider
  (it checks pipeline behaviour and is NOT a quality measurement), a budget-guarded live suite and
  reports. No live evaluation has been run and no model is chosen: the owner's spend cap is $0, so
  `selection.toml` has `total_usd_cap = 0.0` and the live suite refuses at preflight.

- M6: report approval gate and export under `/v1/reports` (hash-bound revisions, approve or
  reject, finalize, Markdown and JSON export, append-only history and audit; migration 0009,
  ADR-0028).
- W8 (ADR-0027): review API routes, production `run_review` registration and Anthropic provider configuration, off unless `EG_REVIEW_PROVIDER` and `EG_REVIEW_MODEL` are set; in-flight reviews per tenant capped by `EG_REVIEW_MAX_IN_FLIGHT` (default 2, 429 over the cap).
- Working agreement moved to `AGENTS.md`; every change now goes through a reviewed pull request.
