# EvidenceGuard

An auditable multi-agent review service for vendor risk. A reviewer uploads a vendor's documents (security questionnaires, policies, reports). EvidenceGuard indexes them, runs a set of review agents over the evidence, and produces a structured report in which every finding points back to a verbatim quote from a source document. A human approver then reviews, revises, approves and finalizes the report before it can be exported.

It is a pre-alpha portfolio project. Nothing is deployed and no live language model has been run against it. See [Limits](#limits).

## What it does

- Tenant-scoped API (FastAPI) with API-key authentication and roles (reviewer, approver, admin).
- Document upload, revisioning, text extraction, chunking and embeddings stored in PostgreSQL with pgvector.
- Hybrid retrieval (full text plus vector search, fused with reciprocal rank fusion) over a frozen snapshot of a review's documents.
- A durable job queue and worker that run indexing and review stages with leases, retries and fencing.
- A review pipeline whose model output is validated against a strict schema and checked so that every cited quote appears in the cited source. The output is stored once and hashed.
- A report workflow: hash-bound revisions, approve or reject, finalize, and export to Markdown or JSON. An append-only history and audit trail is enforced by database triggers.

## Architecture

```
client -> API (FastAPI) -> PostgreSQL 17 + pgvector <- worker (jobs: ingest, index, review)
                                                          |
                                                          +-> model provider (off by default)
```

Code lives in `apps/` (API, worker) and `packages/` (domain, persistence, retrieval, agents, observability). Decisions are recorded in [docs/decisions](docs/decisions), the original plan in [docs/plan.md](docs/plan.md), and the threat model in [docs/threat-model.md](docs/threat-model.md). The architecture is described in [docs/architecture.md](docs/architecture.md). Responsible-AI notes are in [docs/responsible-ai.md](docs/responsible-ai.md).

## Run it

Requirements: Python 3.12, [uv](https://docs.astral.sh/uv/), and PostgreSQL 17 with the pgvector extension.

```
uv sync
uv run pytest               # unit tests, no database needed
```

Configuration is read from environment variables only (no `.env` file is loaded; see `.env.example` for the names). Integration tests need a disposable database whose name ends in `_test`:

```
EG_TEST_DATABASE_URL=postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/evidenceguard_test \
EG_REQUIRE_INTEGRATION=1 uv run pytest -m integration
```

A Docker Compose file (`docker-compose.yml`) runs the API, worker and database. It is exercised by the CI container job.

Model-backed reviews are off unless `EG_REVIEW_PROVIDER` and `EG_REVIEW_MODEL` are set; the provider key (`EG_ANTHROPIC_API_KEY`) is read by the worker only. With them unset, the review endpoint answers 503.

## Design decisions

- Fail closed: reviews, spend and exports are refused unless explicitly configured.
- Evidence first: a finding without a verbatim, verifiable quote is rejected.
- Human in the loop: model output is advisory; export requires an approver to finalize a revision they did not write.
- Immutability: review outputs are write-once and hash-bound; history tables refuse UPDATE and DELETE.
- Least privilege: the API never holds the model key and never calls a model.

## Tests and CI

Tests cover unit, PostgreSQL integration, installed-wheel and container checks. GitHub Actions runs them on Ubuntu and Windows plus a secret scan.

## Evaluation

Evaluation: see [docs/evaluation.md](docs/evaluation.md).

No live evaluation has been run and no model has been selected.

## Limits

- No live model has been run, no model has been selected, and there are no quality, cost or latency figures.
- No frontend. Single region. Nothing is deployed.
- The in-flight review cap limits concurrency per tenant, not total spend.
- Append-only protection assumes the runtime database role does not own the tables.
- No rate limiting on the API.
- Retrieval ties are broken by chunk id, so rankings can differ between fresh databases.
- All data in this repository is synthetic.

## License

No license has been chosen yet; all rights reserved by the author.
