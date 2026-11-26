# Threat model

## v0.1 summary

This summary describes the system as it is in v0.1. The sections after it are the detailed record
for each component, written as each part was built; their headings name the milestone in which
that part was added, and where their wording about what is or is not implemented differs from
this summary, this summary is current. How the parts fit together:
[architecture.md](architecture.md).

**Trust boundaries.**

- **API clients** are authenticated by bearer API keys; only the key prefix and the SHA-256 of
  its secret are stored. The tenant, user and role come from the stored key, never from the
  request (`apps/api/evidenceguard_api/auth.py`).
- **Uploaded documents are untrusted.** Uploads are size-bounded and strictly decoded
  (`apps/api/evidenceguard_api/uploads.py`). Document text reaches a model only as JSON data,
  and the prompts instruct the model to treat it as content, never as instructions.
- **Model output is untrusted.** Replies are schema-validated and every quotation is matched
  against the passages retrieved for that question before anything is stored
  (`packages/domain/evidenceguard_domain/provenance.py`).
- **The model provider** is an external service reached only by the worker, only when a deployer
  enables reviews (`EG_REVIEW_PROVIDER`, `EG_REVIEW_MODEL`; off by default). The provider key
  `EG_ANTHROPIC_API_KEY` is read by the worker only; the API never reads it and never calls a
  model (`apps/worker/evidenceguard_worker/review_wiring.py`).
- **The database** is trusted. The application enforces tenancy with composite tenant keys and
  tenant-filtered queries; PostgreSQL row-level security is not used.

**Roles.** `reviewer` and `approver` may use vendors, documents, reviews and reports; only
`approver` may approve, reject or finalize, and never a revision they authored; `admin` is an operator role that is refused on those routes (`packages/domain/evidenceguard_domain/context.py`).

**Model outputs are advisory.** A review produces a draft. Export requires a finalized report,
finalizing requires an approval, and an approval binds one exact revision number and SHA-256
(the approval gate, [ADR-0028](decisions/0028-approval-gate-and-export.md),
`apps/api/evidenceguard_api/reports.py`). See [responsible-ai.md](responsible-ai.md).

**Not measured.** No live evaluation has been run and no model has been chosen. There are no
quality figures, and prompt-injection resistance has not been measured.

**Data handling.** The repository holds synthetic data only. Document text is sent to a model
provider only when a deployer enables reviews, and only from the worker. Logs carry reviewed
event names and allowlisted fields, never document text, prompts, replies or keys.

**Known limits in v0.1.**

- Append-only protection of report history and audit rows is a database trigger that a table
  owner or superuser can disable; it holds only while the runtime role does not own the tables,
  which nothing in the repository enforces.
- No request rate limiting, lockout or key expiry. Reviews have a per-tenant cap on jobs queued
  or running (`EG_REVIEW_MAX_IN_FLIGHT`), which bounds concurrency, not spend.
- A GET on a report can write (the first access creates revision 1).
- Exports are not signed; their digest can be compared with the audit row.
- No TLS, secrets manager or production deployment; the Compose stack is for development.
- Provenance is checked, semantic support is not; document authenticity is never established.

## Scope and assets

EvidenceGuard helps a reviewer draft a vendor-risk report from uploaded vendor documents. The assets to protect are:
- each tenant's documents, evidence and reports;
- the integrity of report content and of the approval history;
- credentials (API keys, model-provider keys).

Only synthetic demonstration data is used.

## What is implemented and tested now
These are **domain invariants** in `evidenceguard_domain`, enforced by validation and pure functions and covered by unit tests:

| Threat | Invariant |
|---|---|
| Evidence from one tenant appearing in another tenant's report | Citations, findings and report content must all carry the report's tenant ID; mixing tenants fails validation. |
| An actor acting on another tenant's report | Every transition checks that the actor's tenant matches the report's tenant. |
| Approving content that was never reviewed, or approving a stale revision | Approval names the exact current revision number and its SHA-256 content hash. Any mismatch is rejected. |
| Editing a report after approval and exporting it as approved | A new revision removes the effective approval. Finalization needs an approval of the exact current revision and hash. Only finalized reports are exportable. |
| Reusing an approval from another report, tenant or revision | Decisions are bound to tenant, report, revision and hash; the report aggregate rejects any decision that does not match. |
| Building an "approved" or "finalized" report object without a decision | The stored status must equal the status derived from the decision history. |
| Changing content after its hash was computed | Domain values are frozen and use tuples, not lists or dicts. `model_copy` re-validates. |
| Claiming support without evidence | Supported or conflicting statuses require citations; the status must match the cited source types. Conflicting evidence needs at least two distinct quotations. That is a structural check, not proof of a contradiction. |
| A report silently dropping a question it could not answer | Every question must be resolved by a finding or listed as unresolved. A vendor claim never resolves a question that requires documentary support. Any question named by a `missing` finding must be listed as unresolved, even if another finding supports it. |
| A rejection with no stated reason | Every rejection decision must carry a non-blank comment, including one built directly. |
| A retry quietly overwriting or discarding who decided what | Only an identical retry (same actor and comment) is idempotent, and it keeps the original decision and time. A changed request raises `DecisionConflictError` instead of being dropped or recorded twice. |
| Privilege escalation through an admin role | Only the approver role can approve, reject or finalize. The `admin` role (M2b) is in neither the report-editing nor the approval set, so it cannot draft, revise, approve, reject or finalize; tested. |

These invariants hold only for code that goes through the domain models and transitions. Pydantic's `model_construct` and `object.__setattr__` can bypass validation; domain code never uses them.

## API request handling
| Threat | Mitigation |
|---|---|
| Submitted values, credentials or quotations leaking into logs | Records rendered by the configured JSON formatter carry only a fixed event identifier (from a reviewed template table; message text and arguments are never formatted) and allowlisted fields: request ID, method, route template, status, duration and exception class. Uvicorn's access log is off. Handlers configured outside `logging_config()` are not covered. |
| Exception text or tracebacks leaking to clients or logs | Unexpected errors return a generic 500 problem. Logs record the exception class only, with no message and no traceback. |
| Validation errors echoing input | 422 problems list only `loc` and `type` for at most 20 errors. Values, messages and context are omitted. |
| `HTTPException.detail` echoing submitted values or internal text | Ordinary HTTP errors get a generic detail for their status class. A specific message must come from the reviewed `PublicMessage` catalogue through `PublicHTTPException`. |
| A client-chosen request ID being trusted | Only a single valid UUID is accepted, and it is used purely for correlation, never for identity or authorization. |
| Request context bleeding between concurrent requests | The request ID is held in a per-task `ContextVar`; tested with ten interleaved requests. |

The full design and limits are in [ADR-0002](decisions/0002-request-ids-logging-and-errors.md). A client-chosen extra field *name* can still appear, capped, in a 422 body.

## API-key authentication
| Threat | Mitigation |
|---|---|
| A client choosing its own tenant, user or role | The principal is derived only from the stored key, user and tenant rows (the key joined to its user on `tenant_id` and `user_id`). `/v1/me` takes no parameters; tenant headers and query values are ignored. Tested with spoofed headers and query parameters. |
| Stolen database contents revealing usable keys | Only the public prefix and the SHA-256 of a 256-bit random secret are stored. |
| Distinguishing why a credential failed | Missing, repeated, oversized, malformed, unknown, wrong-secret and revoked credentials all get the same 401 body and `WWW-Authenticate: Bearer`. An unknown prefix still performs a digest comparison. |
| Credentials leaking into logs, errors or representations | Keys are carried only in masked `SecretStr` wrappers. Request logs keep only allowlisted fields (tested against rendered and raw records). Errors never echo the header. `eg-admin` prints a new key once, to stdout, after commit, and never takes secrets as arguments. Its usage errors print only static usage and a fixed message, never the submitted arguments. |
| A revoked key or demoted user keeping access | No caching: each request reads the current revocation state and role. Tested with role changes and revocation. |
| Database or configuration errors leaking details | They return a generic 503 with no URL, exception text or credential. |

## Tenant-scoped vendors and readiness
| Threat | Mitigation |
|---|---|
| Reading or creating another tenant's vendors | Every vendor query takes the authenticated `ActorContext` and filters by its tenant in SQL. A vendor is read by `(tenant_id, id)` together; the list and its count use the same filter. Create takes the tenant only from the key. Tested with spoofed headers, query parameters and body fields. |
| Learning that another tenant's vendor exists | A foreign ID and a nonexistent ID return the same generic 404. Duplicate slugs are checked only within the caller's tenant. |
| Supplying a tenant, actor or role in the body | `VendorCreate` accepts only `slug` and `name`; any other field is a 422. |
| Privilege use by administrators | Admin keys get a generic 403 on vendor routes. |
| Partial writes after a failure | Each operation is one transaction: commit before the response, rollback on any error (including commit failure), session always closed. Only the vendor slug unique constraint is reported as a 409. |
| Readiness leaking internals or changing the database | `/readyz` returns only fixed check names and states, never URLs, revisions, SQL or errors. It reads `alembic_version` in a rolled-back, time-limited transaction and never migrates or creates anything. |
| A slow or unreachable database tying up the API | Connection (5 s), pool (10 s) and readiness statement (2 s) timeouts. Database work runs in worker threads, not on the event loop. |

**Limits** (ADR-0006): offset pagination is not a snapshot; readiness checks connectivity and revisions only; `/readyz` is unauthenticated; the API-key limits above still apply.

## Durable job core
| Threat | Mitigation |
|---|---|
| Two workers processing one job | Claims take rows with `FOR UPDATE SKIP LOCKED` in one short transaction; a claimed row is running with one owner. |
| A stale worker writing after its job was reclaimed | Every effect and transition runs in a fenced transaction: lock the job row, then re-check the `(job, worker, attempt)` token and an unexpired lease with fresh `clock_timestamp()` in a separate statement. `attempt` grows on every claim, so even the same worker ID cannot reuse an old attempt. |
| A decision based on time read before a lock wait | Ownership is checked only after the lock is acquired, with database time read after the wait; worker clocks, `now()` and `CURRENT_TIMESTAMP` are never used for leases. |
| Committing partial handler work by accident | The fence owns its transaction: it commits only when its block finishes and rolls back on any uncaught error, including a failed commit. `FencedSession` omits `commit`, `rollback` and `close`, so ordinary session calls cannot end the transaction early. This guards against mistakes by trusted handler code; it is not a sandbox (see the limits below). |
| Tenant confusion in jobs | A job's tenant comes from the authenticated actor at enqueue; payloads may not carry tenant fields; `tenant_id` references `tenants`. |
| Data leakage through jobs | Payloads hold only identifier keys and canonical UUID strings (at most 4,096 canonical bytes, enforced by the application); `last_error` holds fixed codes only; errors carry fixed messages. |
| Exhausted jobs blocking the queue | A bounded `SKIP LOCKED` sweep marks them `dead`, and claim selection excludes them. |

**Limits** (ADR-0007): handlers are trusted code, and the fence assumes they preserve its transaction and lock. `execute` accepts arbitrary SQL and Python exposes the underlying objects, so a handler that issued transaction-control SQL, used the underlying connection or edited ownership fields could defeat the fence. A fenced transaction that passed its check just before expiry may commit shortly after the lease expires; the database enforces only that the payload is a JSON object, not the finer payload rules or the byte cap; at the M3a and M3b baselines the worker had no production handlers (M3d, on `main` since `cdf7260`, registers `ingest_revision`). Passing tests demonstrate the tested behaviour, not a general security or performance guarantee.

## Worker runtime
| Threat | Mitigation |
|---|---|
| A stale worker recording an outcome after losing its lease | Outcomes are written only through the fence, after both job threads are confirmed stopped. Lease loss (a refused heartbeat, a refused fenced write, or a passed local deadline) is latched irreversibly and suppresses every outcome. |
| Two jobs, or a lingering thread and a new job, in one process | At most one handler runs at a time. After every bounded wait the runtime checks that the handler and heartbeat threads really stopped; otherwise it stops claiming for good and the CLI ends the process (exit 5). |
| A contradictory second outcome after an atomic finish | `committed` is published only after the transaction context exits successfully; afterwards no completion, retry or failure is attempted. A commit that raises is `uncertain`, is never reported as success, and any recovery stays fenced. |
| A heartbeat refusal caused by the job's own commit read as ownership theft | A refusal during a finish stays pending and is classified only once the finish resolves. |
| A late heartbeat reviving a cancelled attempt | Cancellation and lease loss cannot be cleared; a late renewal moves no deadline and permits no write. |
| Handler work after cancellation or lease loss was latched while a fence waited for its lock | Permission is checked again after the fence acquires its lock, and before an atomic finish records success; a failed check rolls the transaction back before the block runs or commits. |
| An unexpected supervisor failure leaving job threads behind | Cancellation is latched, heartbeats stop and the started threads are joined for a bounded time; no outcome is recorded and no further claim is made. A thread still alive makes the result abnormal, and the CLI exits 5 even if later cleanup fails. |
| Sessions shared across threads | Every M3a call opens its own session; a test records the thread that uses each session. |
| Leaking private values in worker logs | Fixed reviewed events only; the new fields are filled from validated identifiers and enums; no tenant IDs, payloads, idempotency keys, URLs, SQL, exception text or tracebacks. CLI usage and configuration errors print fixed messages. |
| An empty or misconfigured deployment polling forever | With no registered handlers `eg-worker` exits 4 before reading database settings; the claim filter means unhandled kinds stay queued for a capable worker. |

**Limits** (ADR-0008): execution is at least once, so durable effects must be fenced and idempotent, and effects outside the database can repeat. Cancellation is cooperative: Python cannot stop a running thread. `claim` and outcome recording are synchronous and there is no worker statement timeout, so there is **no total shutdown deadline** and a hung call may need external termination. Engine disposal does not cancel checked-out connections; PostgreSQL rolls back a dead worker's transaction only when it detects the disconnect. Reclaim can be delayed by a late heartbeat or a lingering transaction. Handlers are trusted code; the handler wrapper is not a sandbox. At the M3b baseline there were no production handlers.

## Documents and revisions
Reviewed and verified in CI on branch `feat/document-revisions` at commit `8646b75`, then fast-forwarded onto `main` at `6f8ffde`, where CI passed again. The mitigations below were exercised by M3c's PostgreSQL integration tests: constraints, migration, concurrency, activation and lease loss.

| Threat | Mitigation |
|---|---|
| A document or revision linked across tenants | Composite `(tenant_id, …)` foreign keys to vendors and documents; the active and successor pointers reference `(tenant_id, document_id, id)`, so they can only name a revision of the same tenant and document. Every query filters by the actor's or the job's tenant. |
| A job naming another tenant's revision | The revision is looked up only in the job's tenant and is then not found; after the locks, the re-read job's tenant and the document's tenant must match, or the operation is refused before any write. |
| A stale or expired worker activating a revision | After the document and revision lock waits, ownership is re-checked against the locked job row with fresh database time; a stale attempt or an expired lease raises `LeaseLostError` before any write. |
| Two active revisions, or a pointer to a non-active revision | A partial unique index allows one `active` revision per document; activation runs under the document lock and writes demote → promote → pointer in one transaction. Pointer consistency itself is an application invariant (no triggers). |
| A failed or late replacement replacing good content | A failure touches only its own revision; a late older revision becomes `superseded` without touching the active one or the pointer. |
| Content altered between upload and hashing | The hash and size come from the exact bytes, with no newline, BOM or Unicode normalization; stored content is re-verified when reconstructed. |
| Document text leaking through errors or logs | Content types have fixed messages and a content-free `repr`; snapshots and revision reads exclude the text; M3c logs nothing. |
| Concurrent uploads allocating the same number | Numbers are allocated under the document row lock; unique constraints back this up and map to a fixed error. |

## Document ingestion
Reviewed and verified in CI at `74904e6` on `feat/document-ingestion`, then on `main` at `cdf7260`. The mitigations below are covered by the database-independent tests and by the PostgreSQL integration suite, which passed in full in CI.

| Threat | Mitigation |
|---|---|
| Chunks linked across tenants or revisions | `chunk_sets` references the revision through `(tenant_id, revision_id)`; `chunks` references its set through `(tenant_id, revision_id, chunker_version)`; chunk IDs include the tenant and revision, so identical bytes in two tenants get disjoint IDs. |
| A stale worker writing or activating chunks | Every write and the activation run in the M3a fence, take the document and revision locks, then re-check ownership with fresh database time, and re-check again before the write commits. |
| Chunks written after a revision settled or failed | Writes, activation and failure all take the same document lock first; a write re-reads the status under that lock and is refused unless `processing`. |
| An incomplete or different chunk set becoming active | Activation verifies, under its locks, the stored set's version, count, exact ordinals and rebuilt manifest against the current attempt's own expected manifest, in the same transaction as the job's success. |
| Existing chunks silently replaced or accepted | Inserts never overwrite; every existing row is compared field by field, text included, and a missing row after a suppressed conflict is a fixed conflict error. |
| Source text altered or lost by chunking | Chunk text is an exact source slice; only a BOM, line terminators and permitted spaces and tabs may be omitted; stored content is re-verified against its hash before parsing. |
| Document text leaking through errors or logs | Chunk and source values have content-free `repr`s; parser and store errors have fixed messages; the handler logs nothing. |
| Pathological input exhausting resources | At most 4,096 chunks per revision, 4,000 code points per chunk, and bounded write batches. These are initial defaults, not measured limits; there is no upload size limit until M3e. |

## Document API
| Threat | Mitigation |
|---|---|
| Oversized or endless uploads | Caps on the streamed count, never on `Content-Length`: 2 MiB of file bytes, 2 MiB + 64 KiB in total, 8 parts, 8 KiB of headers per part, 1 KiB per text field. Reading stops at the first error; a declared length over the cap is refused before reading. The file is one bounded in-memory buffer and no temporary file is created. |
| Reading a body before authorization | The route declares no body parameters; authentication, the role check and the vendor lookup finish before the first `receive`, which raw-ASGI tests assert. |
| Truncated or malformed multipart accepted | The parser's `finalize()` is a no-op, so the reader requires the closing boundary and every begun part to have ended; a truncated body is never a 2xx. |
| Outcomes depending on how bytes arrive | Header and boundary regions are fed to the parser one byte at a time and part data in slices that stop before each delimiter, so the first error in byte order wins for any receive partitioning; tests cover single, split and random partitions. |
| Header bytes hidden from the cap | The 8 KiB per-part cap counts the raw header region as received (names, colons, whitespace, values and line endings), not names and values reconstructed from parser callbacks, which omit some bytes. |
| Parameters hidden from validation | `Content-Disposition` and `Content-Type` parameters are parsed without dropping extended (`filename*`, `charset*`) or repeated names, so they cannot evade the no-filename rule or the UTF-8 charset rule. |
| Tenant or role injected through the form | Only six known part names are accepted; any other name, including `tenant_id` or `role`, is a 422, and the tenant comes only from the API key. |
| Submitted values leaking through errors or logs | 422 entries carry fixed locations and types; unknown names, filenames, values and parser messages are never echoed. The parser's own logger is disabled, and the only new log event (`document.upload_inconsistent`) carries no values. |
| A revision without its job, or a job reset by a re-upload | Revision and job are created in one transaction; a duplicate never resets or re-queues an existing job and never re-enqueues a settled revision. |
| Content, payloads or worker IDs exposed by reads | Revision views never select `content_text`; job views omit the payload, idempotency key, worker ID and tenant; response models forbid extra fields. Objects of other tenants are 404. |
| Inconsistent or misleading status | Each GET is one REPEATABLE READ, READ ONLY snapshot with one database time; `ingestion_state` is derived, `in_progress` shows `lease_expired`, and `verified_complete` is true only for active or superseded revisions. |

**Limits** (ADR-0011): the reader depends on the verified behaviour of `python-multipart` 0.0.32, which an upgrade must re-verify. Per-byte header feeding costs CPU bounded by the header caps. The upload response is an observation that a worker may change at once. `stalled` revisions have no operator retry in v1.

## Containers
- the effective build context excluded all 19 planted fixtures;
- the runtime ran as UID/GID 10001;
- the application containers ran the CI-built image;
- the smoke passed, including its key-in-service-logs check and the idle-worker exit check;
- cleanup verified ownership.

| Threat | Mitigation |
|---|---|
| Secrets or artifacts entering the image | The build context is an allowlist with recursive re-exclusions (`.env*`, `.git`, `.local`, virtual environments, caches, build outputs, keys). CI is to verify the effective context with planted nested fixtures. The runtime image holds only the virtual environment and `alembic.ini`, with no build arguments or baked-in configuration. |
| A substituted or unexpected image | Base images and the database image are pinned by digest. Application services never pull (`pull_policy: never`), and CI is to check that every application container runs the CI-built image ID. |
| Excess privilege in containers | UID/GID 10001; root-owned files the runtime user cannot modify; a read-only root filesystem with a `/tmp` tmpfs; all capabilities dropped; `no-new-privileges`; an init process. |
| Exposure on the network | Host ports bind `127.0.0.1` only (API 8000, database 5433). |
| Migration races | Only the one-shot `migrate` service migrates; the API and worker start after it succeeds. |
| The CI API key leaking into logs | The key stays in memory. Every key-shaped string from `create-key` is protected before its status or format is checked, and its raw output is never shown. Captured output is redacted before display, including anything key-shaped. Unavailable service logs fail the smoke rather than passing the key check, and a key found in service logs fails it (reported as a count). GitHub masking is only an extra layer. |
| Cleanup removing unrelated resources | Cleanup removes only resources labelled with this run's Compose project and this run's image tag, after checking that both name the same run and attempt. It refuses `down` when ownership cannot be verified, and reports success only after a successful post-cleanup verification. |

**Limits** (ADR-0012): the database credentials are disposable and public. Stopping the worker has an external 60 s budget, not a guaranteed shutdown bound (ADR-0008). The smoke stops an idle worker only. Cleanup can be prevented by runner loss. The uv builder-tool image is used under a narrowly approved exception to the two-week age policy, for its exact digest only (no runtime uv; no change to the Python base or the general policy). The exception does not claim age compliance or general safety. There is no production deployment.

## Revision indexing
specification ([ADR-0015](decisions/0015-revision-indexing.md)). The complete corrected implementation

neither Codex nor the reviewer ran those checks.

| Threat | Mitigation |
|---|---|
| Indexing another tenant's revision | The tenant comes only from the validated actor (enqueue/backfill) or the job (handler). Every selection, enqueue and read is tenant-scoped, and M4b's composite keys back this in the database. |
| Unauthorized or unbounded operator action | `eg-admin backfill-indexes` follows the existing trusted-operator model, with no API endpoint. It processes one bounded page (limit 1–100) per invocation, never retries or resets a terminal job, and prints only fixed outcome counts and the cursor. |
| Leaking text, vectors or keys | Job payloads hold only `index_id`. Page values and errors never show text or vectors, the handler does not log, and CLI and runtime output carry fixed counts and codes only. |
| An unexpected or networked provider | Providers come only from an immutable mapping fixed when the handler is built (production: the offline `HASH_IDENTITY`). The stored identity's fingerprint is verified before resolution, and no live adapter, network or environment is used. |
| Stale writes after cancellation or lease loss | Provider work runs with no transaction or lock open. `ctx.check()` runs before and after it (and before classifying a provider or provider-resolution failure), each write and the finish are fenced, and M4b re-checks ownership. Cancellation, lease loss and fence closure raised during provider resolution propagate unchanged. Readiness and job success commit together. |

**Limits:** checks happen at explicit boundaries only. They do not interrupt synchronous calls,
and a cancellation latched after the last check may not stop a non-finish transaction already
under way; the accepted lease-expiry/commit window remains. Reused committed vectors are not
re-verified against provider output, and provider calls are not exactly-once. A stalled index
(terminal canonical job) has no recovery in M4c, and activation does not enqueue indexing
automatically. The container smoke covers idle-worker shutdown only. The offline provider is a
lexical-hash baseline with no semantic-quality claim, and no live provider was verified.

## Snapshot retrieval
The M4d specification

([ADR-0016](decisions/0016-snapshot-retrieval.md)); the correction preserves process-control
exceptions raised during the read helper's setup when cleanup also fails.

| Threat | Mitigation (implemented, accepted and verified in CI on `main`) |
|---|---|
| Retrieving another tenant's or vendor's content | The tenant comes only from the trusted actor (reviewer or approver). Capture is tenant- and vendor-scoped; every channel and evidence statement repeats the tenant, vendor, binding, ready-index and profile joins before its `LIMIT 20`. |
| Silently searching an incomplete or changed corpus | Capture runs in one REPEATABLE READ, READ ONLY transaction and refuses any active revision without a chunk set or ready index for the profile, an empty set and more than 100 revisions or 100,000 chunks. Before every retrieval, one statement rechecks every immutable binding; current `status` is never consulted, so supersession is snapshot-relative. |
| Leaking queries, text, vectors or backend detail | Values show IDs and counts only. Provider and database failures become fresh fixed errors raised outside handlers, with no message, statement, parameter, cause or context; nothing logs. Process-control exceptions propagate unconverted. |
| Unbounded work | 1–8 queries, at most 16 channel statements of 20 rows, k at most 20, a transaction-local 30-second timeout per statement; provider calls run with no session open. |

**Limits:** its accepted trust model keeps a limitation: until M5 persists snapshots, a snapshot
value forged in trusted in-process code could include same-vendor revisions that were superseded
before capture, because retrieval cannot re-prove past eligibility (a PostgreSQL test documents
this); no protection against malicious in-process code is claimed. The precomputed-vector seam
cannot prove that vectors came from the claimed queries. The evidence digest check detects one
class of tampering only; no hash protects against a database writer outside the application.
Repeated table headers are a separate span that citations must not quote across.

## Corpus and retrieval evaluation
The M4e specification

([ADR-0017](decisions/0017-retrieval-evaluation.md)); the

database write, keep process-control exceptions and fixed refusals through read-cleanup failures,
return a created vendor only after its transaction commits, and check per-file sizes (64 KiB for
the manifest, 256 KiB per document or ground-truth file) and the effective set's 4 MiB total before
reading any payload, each read bounded by its checked size. A concurrent file-system change between
check and read is detected only as an observed size or type mismatch, not prevented. It specifies a fictional synthetic corpus
only (no real client data, credentials or personal
data), loading solely through the existing production lifecycle into guarded disposable test
databases, isolation checks that fail on foreign-tenant, cross-vendor or forbidden chunks and
foreign canaries even when Recall is high, and fixed-code diagnostics without document text. It
makes no injection-resistance or semantic-quality claim; end-to-end canary and output behaviour
remain M5/M7.

## Voyage embedding adapter
The M4f specification

closed: a transport `VoyageError` with a missing or raising `code`, and a failing TLS-context
setup, no longer let a raw exception or its text escape; both now give fresh fixed errors.
that adds no mitigation. The implemented controls:

**Timing is cooperative, not a hard deadline:** a 10 s connect timeout, a 30 s socket I/O
timeout per blocking wait and a 60 s elapsed-time budget checked before and after each phase.
The budget cannot interrupt an in-progress standard-library operation. DNS, repeated connection
attempts, TLS, header parsing and internal buffered or chunked reads can exceed it; when the
standard library releases the connection socket after the headers, body reads keep the earlier
socket timeout; and cleanup has no deadline, so **no hard wall-clock maximum is established**;
a hard deadline would need a separately reviewed transport design.

- sending vendor text to a third-party service (a data-handling decision for any live use in
  M7);
- repeated provider calls, since calls are at least once;
- calls running past the nominal budget;
- live vectors that might not meet the 1e-6 norm tolerance after float32 rounding (rejected,
  not corrected).

The settled decisions, details and the unresolved external API facts are listed in the plan.

## Review workflow
The M5 implementation sequence
and the M5a specification

| Threat | M5a control (on `main` at `f04e0957`, verified in feature and main-push CI) |
|---|---|
| Malformed, ambiguous or oversized model output treated as valid | Python-mode entry points, including `model_validate_strings`, never coerce raw strings into enums or other types. A bounded preliminary JSON scan (duplicate keys, non-finite numbers, trailing text, top-level shape, depth 8, 2,000 values, 65,536 bytes) and strict JSON-mode validation against a closed, purpose-specific, deeply immutable schema; any failure is `invalid_output`. The model never supplies status, source type, tenant or revision fields. |
| Provider failures, refusals or wrong models silently accepted | `call_validated` revalidates the request and the response, calls the provider at most once and turns every ordinary failure into a fixed outcome; a model mismatch wins over any stop kind. |
| Model output or evidence leaking through errors, representations or logs | Fresh fixed errors with no cause or context, raised after one boundary around each whole public operation; `hide_input_in_errors`; count-only representations of every value; no logging. Process control propagates unchanged. This normalizes errors for supported inputs; it is not a sandbox against malicious trusted code. |

These controls are local to the M5a values: **no review path uses them yet**, nothing registers or
configures a model provider, and the scripted fake is a test fixture. The remaining controls below
are specified for later slices (M5b–M5h) and **do not exist or operate yet**; their details still
need their own reviewed specifications. The privacy scope excludes trusted code inspecting frame
locals or held values, and the call boundary imposes no hard deadline on a provider. Specified for
later slices: every ordinary model-provider failure becomes a fixed outcome that
leaves the question unresolved; model output is parsed strictly against a closed, immutable
schema, and validation errors never expose its text; output never supplies status, source type,
tenant or revision; citations must name chunks retrieved for that review and question, with
quotes found in them; evidence enters prompts only inside delimited blocks with document text
safely encoded; review creation captures eligibility and stores the snapshot, configuration and
job in one transaction, and the handler reloads it through a trusted, revalidating path (closing
the M4d in-process snapshot limitation for review paths only, once implemented, and with no
protection against direct database writers or malicious in-process code); call reservations,
stage and output writes are fenced; and no production path can dispatch a review until a reviewed
wiring decision.

implemented

nested aggregate rebuilds; constructors remain consistency checks only), and accepted at external

clarifications.
(implementation status, [ADR-0024](decisions/0024-review-report-content.md)).

[ADR-0025](decisions/0025-review-orchestration.md)). Its feature CI at `f0d4ce92` failed: the
PostgreSQL job ran with one failure, an invalid cross-question test comparison corrected in

(reviewer logs).

- **Process control on fenced paths:** `transaction()` now keeps the first process-control
  object by identity across body, commit, rollback and close (G15). Its non-database tests
  pass; no rollback, disposal or commit outcome is claimed.
- **Context-exit privacy:** unclassified ordinary failures leaving a fenced block are replaced
  by the fixed `ReviewFenceExitError`, so no SQL, parameter or database text reaches job errors
  or logs (G22). This is tested with sentinel text against fake sessions only.
- **Atomic output:** the output row and the job's success share one finish transaction. Their
  PostgreSQL tests are among the positions that passed in the green `3d41f435` integration job
  (reviewer's logs, which print positions rather than test names).

None of this operates in an application review path: no endpoint, command or production
registration builds the handler, no live provider is configured, and `run_review` remains
unregistered.

- **Basis.** Source inspection and the complete passing PostgreSQL module results. The logs
  print positions, not names, so the replacement-activation result is inferred from the source.
  That is an evidence-granularity limitation, not an implementation gap.
- **Not accepted.** Production wiring and overall M5.
- **Retrieval APIs.** Explicit-snapshot retrieval (`search_snapshot`) still relies on a trusted
  caller. `capture_snapshot` and `capture_in_transaction` capture snapshots rather than accept
  one, and `search_current` intentionally selects current state. The internal handler uses only
  its trusted persisted snapshot, and any future production registration needs its own
  composition review.
- **Unchanged.** U4's discarded evidence, database trust, the M3 lease/commit window, unknown
  outcomes, M6's approval and export obligations, and the provenance-versus-semantic limits.

(decision and local blocker).
Docker tooling was unavailable locally; no disposable database, control or mutation ran, and
no task container/storage was created.
permits execution of the same mutations in the existing disposable CI PostgreSQL service
(separate amendment and runner preparation).
The isolated-copy runner/additive step was accepted for one local commit and manual feature

The accepted sequence also requires that every conclusion shown in an approval or export artifact
be in its canonical hashed content, or derived solely from it, so no displayed conclusion can come
from unhashed stage rows.

## Reports, approval and audit
Routes under `/v1/reports` ([ADR-0028](decisions/0028-approval-gate-and-export.md)) expose a
completed review's stored output as a report with hash-bound revisions, approval or rejection,
finalization and export.

- **Tenant and roles.** The tenant comes only from the API key; every query filters by it, and
  another tenant's report is indistinguishable from a missing one (404). Reviewers and approvers
  may read, revise and export; only approvers may approve, reject or finalize; administrators get
  403 everywhere. An approver may not approve, reject or finalize a revision they authored.
- **Integrity.** Each revision binds tenant, report, review and the exact wrapper SHA-256, and its
  hash covers that digest. Approvals and finalization bind the exact revision number and hash by
  composite foreign keys. Mutations are compare-and-set under a row lock (`If-Match`, ETag
  `"r{n}-{sha}"`), so a stale request is refused rather than applied.
- **Export.** Only finalized reports, rendered from the stored, digest-checked revision and
  wrapper bytes; no stage or plan rows are read. Reviewer-supplied text is emitted as escaped
  JSON literals. The export carries a fixed disclaimer: AI-assisted, citations show provenance
  only, not legal advice or certification.
- **Audit.** Every revise, approve, reject, finalize and export writes one audit row with actor,
  revision and hash (and, for export, format and body SHA-256) in the same transaction. A trigger
  rejects UPDATE, DELETE and TRUNCATE on the history and audit tables, and DELETE and TRUNCATE on
  `reports`.

**Limits.** The triggers protect against application code and ordinary roles only: a table owner
or superuser can disable or drop them, so this guard depends on the runtime role not owning the
tables, which the deployment does not yet enforce. A GET can write (the first access creates
revision 1). Exports are not signed, so a downloaded file proves nothing on its own; its digest
can be compared with the audit row. Downgrading migration 0009 deletes all report and audit data.
There is no rate limiting on these routes. Each export appends an append-only audit row, so audit
growth is bounded only by request volume; rate limiting is out of scope for v0.1.

## Open risks

- **Prompt injection.** Uploaded documents are untrusted and may contain instructions aimed at the model. Mitigations: delimited evidence, no model tools, schema-validated output, verbatim quote checks and a human approval gate. Resistance has not been measured.
- **Semantic support.** The quote check proves a quotation exists in a retrieved passage, not that the passage supports the claim. That needs the human reviewer.
- **Database trust.** The database and its operators are trusted. Append-only history depends on the runtime role not owning the tables, which is not enforced.
- **No rate limiting, lockout or key expiry.** Audit and review volume are bounded only by request volume and the per-tenant in-flight cap, which limits concurrency and is not a spend limit.
- **Transport.** The services speak plain HTTP; TLS termination is the deployer's responsibility.
- **Retrieval ties.** Ties are broken by chunk id, so rankings can differ between fresh databases.
- **Secrets.** Database URL and API keys are held as masked secrets. The model key is read only by the worker. Other secret handling is a deployer concern.
