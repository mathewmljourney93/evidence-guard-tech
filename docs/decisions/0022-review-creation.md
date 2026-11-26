# ADR-0022: Composable capture, atomic review creation and trusted reload

  External review).
  implementation was staged and implementation acceptance was pending, and at that acceptance
  publication, Linux verification, PostgreSQL execution and current-version CI were pending.
  **Since then:** feature branch `1bea3731` was published; Ubuntu and Windows verify passed; PostgreSQL executed and failed three tests; the test corrections were staged, committed as `1efe3ed3` and published to the feature branch, where all five jobs passed; `main` was fast-forwarded to `1efe3ed3`, and M5d is **reviewed, verified in CI and on `main` at `1efe3ed3`** (feature and main execution evidence independently retrieved by the external reviewer; the main integration job's top-level API status stayed `in_progress` with no conclusion although its steps, its complete log and its parent run succeeded).
  Feature and main CI evidence,
  Exact-commit CI and PostgreSQL test corrections and
  External review). No endpoint, CLI command, handler,
  setting, production registry entry or production enqueue path uses M5d: creation and reload are
  internal or test-only seams and `run_review` is not registered, so none of its controls operates
  in the application, and overall M5 acceptance is pending. PostgreSQL tests were not run locally
  (no test database is configured; see
  Verification).
  Implements the
  accepted M5d specification, the fourth slice of the
  accepted M5 sequence.
- **Date:** 2026-10-22
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (snapshot capture and its race rules),
  [ADR-0019](0019-model-call-contracts.md) (`PromptRef`) and
  [ADR-0021](0021-review-request-assembly.md) (pinned template and prompt loaders).

## Decision

M5d adds a review value module, a bounded database-failure classifier, the composable capture
seam, migration `0006` with three review tables, atomic review creation with idempotent replay,
the trusted reload, and one isolated worker module that composes them with the M5c pinned
loaders. It adds no endpoint, CLI command, production enqueue path, handler registration,
provider, live call, setting or dependency.

**What it establishes.** A review, its snapshot bindings and exclusions, its pinned template,
prompt and model configuration and its `run_review` job are committed together or not at all, in
one REPEATABLE READ, READ WRITE transaction whose visibility follows the snapshot established by
its `clock_timestamp()` read. A tenant-scoped client key replays a matching request (tenant-bound
digest) and refuses a different one. Reload rebuilds every stored value through its constructor
and recomputes and compares the stored digests and the job association. **What it does not.**
The digests detect disagreement between stored rows only; nothing protects against direct
database writes or malicious trusted in-process code. The M4d trusted-snapshot limitation closes
for review paths only once M5g obtains its snapshot solely through this reload; it is **not**
closed by this slice. Timeouts bound individual statements and lock waits, not the operation.

## Modules and public contract

| Path | Contents |
| --- | --- |
| `packages/domain/evidenceguard_domain/reviews.py` (new) | `ReviewConfiguration`, `ReviewRequest`, `CreatedReview`, `TrustedReview`; `request_canonical_object`, `request_canonical_bytes`, `request_sha256(request, *, tenant_id)`, `rebuilt_request`; the fixed review errors |
| `packages/persistence/evidenceguard_persistence/database_failures.py` (new) | `DatabaseFailureCategory`, `RETRYABLE_CATEGORIES`, `classify_database_failure`, `CommitFailureResolution`, `classify_commit_failure` |
| `packages/persistence/evidenceguard_persistence/retrieval.py` (changed) | public `capture_in_transaction` returning `RetrievalSnapshot \| SemanticOutcome \| CaptureFailure`; `capture_snapshot` unchanged in behaviour |
| `packages/persistence/evidenceguard_persistence/models.py` (changed) | `Review`, `ReviewBinding`, `ReviewExcludedRevision` |
| `packages/persistence/evidenceguard_persistence/migrations/versions/v0006_reviews.py` (new) | migration `0006` (down revision `0005`) |
| `packages/persistence/evidenceguard_persistence/reviews.py` (new) | `create_review`, `load_review`, `CommitState` |
| `apps/worker/evidenceguard_worker/review_seams.py` (new) | `ResolvedReview`, `create_review_with_artifacts`, `load_trusted_review` |

Canonical encodings (`eg-review-configuration-v1`, `eg-review-request-v1`) are
`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)` encoded
as ASCII. The request digest takes the tenant explicitly and the seams take it only from the
validated `ActorContext`. The idempotency key never appears in a representation or error.

## Implementation choices and deviations

within the documented scope:

1. **Testable steps.** The creation steps (`_begin`, `_replay`, `_create_job`, `_insert`) and the
   imported `capture_in_transaction` are module-level names, so the control-flow tests replace
   them with recording fakes; the real steps are tested separately against recording sessions
   and, in CI, against PostgreSQL.
2. **Module-decided refusals.** A private `_Refusal` exception carries a fixed error class out of
   the steps (idempotency conflict, job conflict, inconsistent replay record). It is never a
   database error and is never classified.
3. **`capture_snapshot` preserved.** `_capture_body` now calls `capture_in_transaction` after the
   unchanged timeout and turns a `CaptureFailure` into a private `_CaptureFailed`, so `run_read`
   still reports `RetrievalDatabaseError`; the M4d phases moved unchanged into `_capture_phases`.
4. **Replay depth.** A replay checks the stored request digest, validates the job association and
   rebuilds the `CreatedReview` (any failure is `ReviewRecordInconsistentError`); it does not
   rebuild the full snapshot. Full reconstruction happens in `load_review`.
5. **Job creation.** An already visible `run_review` job for the new key is refused before
   `enqueue`; `JobIdempotencyConflictError` and `JobEnqueueRaceError` from `enqueue`, and any
   returned job other than exactly the expected new queued job, are `ReviewJobConflictError`.
6. **Process control first seen during cleanup.** It is the first process-control object of the
   attempt, so it propagates as the same object even after a committed attempt (whose
   `CreatedReview` is then not returned) and no further attempt runs; an ordinary cleanup failure
   after a commit keeps the `CreatedReview`.
7. **Session-factory failure.** With no session there is no cleanup; an ordinary failure is
   classified like a body failure, and a retryable category without normal cleanup ends with
   `ReviewConflictRetryableError` rather than another attempt.
8. **Reload recording session.** `load_review` wraps each session in a private
   `_RecordingSession`, and each result its `execute` returns in a private
   `_RecordingResult`, so the first process-control object raised inside `read_snapshot` (while
   executing, consuming a result or cleaning up) or by the reload body is recorded and re-raised
   even if the helper's cleanup then raises an ordinary exception or a later interrupt.
9. **Seam artifact check.** `create_review_with_artifacts` loads the pinned template and both
   prompts before any session, so an unregistered digest is `ReviewArtifactsUnavailableError`
   without database work.

**Migration-head pins.** Migration `0006` changes the Alembic head and
the table set.
pinned head `0005` (four non-integration tests failed locally);
updating them, as recorded below.

## Exact-commit CI at `1bea3731` and PostgreSQL test corrections

**Failed feature CI.** Feature branch `feat/review-creation` was published at
`1bea3731f965c4555b9dc6bf0d9fa64447bf3789`. Its push runs, attempt 1 for that exact SHA:
[ci 39739061688](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688) (failure) and
[secret-scan 39739061684](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061684) (success). Claude Code observed only the API run,
job and step conclusions; its job-log download returned HTTP 403. The external reviewer then
independently retrieved the run records, job metadata, all five job logs and the relevant
published source; the results below are theirs, and they are results for
`1bea3731`, not for the corrections in this section.

| Job | Reviewer-observed result |
| --- | --- |
| [verify (ubuntu-24.04)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602245) | 3637 passed, 335 skipped; format, lint, mypy, tests, build and installed-wheel steps succeeded |
| [verify (windows-2025)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602154) | 3636 passed, 336 skipped; the same required steps succeeded |
| [integration (PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691602147) | **3 failed, 332 passed, 3637 deselected** |
| [container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061688/job/119691601997) | success |
| [Gitleaks](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39739061684/job/119691601837) | 83 commits scanned, no leaks |

Both verify logs printed these nine installed-wheel result lines: "offline embedding, canonical
storage and indexing modules ran from the installed wheel"; "retrieval modules imported and fusion
ran from the installed wheel"; "evaluation modules imported and Recall@5 = 2/3 computed from the
installed wheel"; "Voyage adapter validated a mocked response from the installed wheel";
"model-call contracts classified a scripted fake response from the installed wheel"; "provenance
matched a quote and derived a status from the installed wheel"; "review template, prompts and
request assembly ran from the installed wheel"; "offline migration SQL rendered from the installed
wheel"; and "offline review migration SQL rendered from the installed wheel". (The earlier local
count of ten lines included the production-registry line; it is Claude Code's historical local
observation, not independently confirmed here.) The container smoke reported: effective build
context 109 files with 19 planted fixtures excluded; database healthy, migrations completed and API
healthy; upload 202 and ingestion succeeded with two verified active chunks; duplicate upload 200
with the same revision; one offline backfill job, two embeddings and a ready index; idle worker
exit 0 without OOM; smoke succeeded. These are the smoke's reported checks; it does not exercise
M5d review creation. The Recall line is arithmetic and the Voyage line mocked; none of these
results establishes live-model quality, injection resistance or production readiness.

**The three failures** (all in `tests/test_reviews_postgres.py`; diagnoses from the reviewer's log
and source inspection):

1. `test_tenants_are_isolated`: the corpus fixture leaves an ingestion job queued; the helper ran
   the worker once for another tenant's revision, the worker claimed the older job, the target
   revision stayed inactive and the indexing enqueue raised `IndexSourceNotEligibleError`. A test
   fixture defect.
2. `test_an_activation_committed_after_the_snapshot_is_established_is_not_bound`: the held
   attempt's `review_bindings` insert failed with SQLSTATE `40001` (the foreign-key check's
   key-share lock on `document_revisions` met the concurrently committed supersession); creation
   retried in a fresh transaction as accepted, the replacement was active but unindexed, and the
   fresh attempt correctly raised `SnapshotNotReadyError`. The test's expectation was wrong, not
   the creation behaviour.
3. `test_creation_returns_its_pooled_connection_with_default_settings`: the listener matched every
   statement containing `clock_timestamp`, which includes the job enqueue's values as well as the
   capture clock read, so it recorded the same backend twice. A test observation defect.

**Per-attempt visibility versus persisted bindings (clarification).** Snapshot visibility is fixed
within each attempt. Only the successfully committed attempt's snapshot becomes the persisted
review snapshot; a rolled-back attempt's `captured_at` and bindings are not promised to survive a
fresh-transaction retry. Once a review has committed, later revision activation does not change its
stored bindings. This clarifies the accepted contract; the retry, classification and transaction
rules are unchanged.

**Corrections.**

- *Target-specific completion.* A test helper `_complete` runs the worker one claim at a time until
  the **target** job has succeeded. It counts all other queued jobs whose kinds the registry can
  run (it does not establish their queue position relative to the target); its loop bound is that
  count plus one, and the caller limits the permitted other queued fixture work (`other_queued`).
  More such work than permitted, a failed target attempt or an exhausted bound fails clearly.
  ** `_ingest` requires the target revision
  to end `active`; `_index` requires it to be `active` before enqueueing and the target index to
  end `ready`. The tenant-isolation test declares the corpus fixture's pending ingestion job as the
  one other queued job; fixtures that need pending revisions are not drained.
- *Concurrent activation.* The misleading test is replaced by three: (a) a concurrent replacement
  left unindexed: two attempts, one attempted and zero successfully executed `review_bindings`
  inserts, the one rejected statement being that insert with `40001`, then
  `SnapshotNotReadyError` and no review, `run_review` job or child row; (b) a concurrent
  replacement fully ingested and indexed before the held attempt is released: the same `40001`,
  then a committed review bound only to the replacement, one review, one binding, one
  `run_review` job (the committed attempt's) and no exclusion row; (c) a review committed before
  a replacement is activated: its reloaded bindings, snapshot and digest and job identity are
  unchanged. Synchronization uses bounded events with `finally` release and listener cleanup;
  failed statements are recorded by a test-owned `handle_error` listener, attempted ones before
  execution and successful ones after it.
- *Pooled connection.* The listener records the backend of every creation statement, and the test
  requires the nonempty set to equal the backend that then serves the settings read; the
  one-connection `QueuePool` and the four default-setting assertions are unchanged.

the feature CI gate at
`1bea3731` failed, and main publication remains blocked until corrected CI passes and is reviewed.

**Local verification.**
Only `tests/test_reviews_postgres.py` changed among code and tests; every production, migration,
model, dependency, packaging, workflow and other test blob is identical to `1bea3731`. `ruff check
.` clean; `ruff format --check .` 211 files formatted; strict `mypy` no issues in 168 source files.
Focused command (`test_reviews_postgres`, `test_review_creation`, `test_review_values`,
`test_database_failures`, `test_persistence`, `test_readiness`, `test_packaging`): 298 passed, 28
skipped (PostgreSQL). Full suite: 3635 passed, 339 skipped, 0 failed (337 PostgreSQL tests, one
symbolic-link test and one POSIX-only signal test); collection 337 integration (one test replaced
by three) and 3,637 non-integration tests (3,974). **PostgreSQL: not run** - the corrected and
new database tests are written but unexecuted; local skips prove nothing about them. No build or
installed-wheel check was repeated: production and packaging blobs are unchanged, and the passing
`1bea3731` verify jobs remain the exact-commit evidence for that published version.

## Limits and later-slice obligations

- Creation and reload are trusted internal seams; M5h owns any transport and M5g the handler and
  orchestration, which must obtain the snapshot only through `load_trusted_review`.
- `Session.invalidate()` reaches only connections still associated with the session's
  transaction; no physical disposal or pool quarantine is claimed.
- An unknown `COMMIT` outcome is never retried automatically; the caller may repeat the request
  with the same key, which replays if the earlier commit succeeded.
- M5e stores planned questions, evidence, call reservations and stages (implemented in Prompt
  200, [ADR-0023](0023-review-stage-persistence.md)); under the E7 scope decision the report
  output and its atomic writer belong to M5f/M5g, not M5e; M5f the report representation; M7
  measures live behaviour. (Historical: this line read "M5e stores stage calls and outputs"
  before E7.)
