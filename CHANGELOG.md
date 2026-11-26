# Changelog

Short record of merged changes, newest first. Details live in each pull request.

## Unreleased

- Architecture guide, v0.1 threat-model summary and responsible-AI statement; a test keeps
  reader-facing pages free of status and result claims.
- M6: report approval gate and export under `/v1/reports` (hash-bound revisions, approve or
  reject, finalize, Markdown and JSON export, append-only history and audit; migration 0009,
  ADR-0028).
- W8 (ADR-0027): review API routes, production `run_review` registration and Anthropic provider configuration, off unless `EG_REVIEW_PROVIDER` and `EG_REVIEW_MODEL` are set; in-flight reviews per tenant capped by `EG_REVIEW_MAX_IN_FLIGHT` (default 2, 429 over the cap).
- Working agreement moved to `AGENTS.md`; every change now goes through a reviewed pull request.
