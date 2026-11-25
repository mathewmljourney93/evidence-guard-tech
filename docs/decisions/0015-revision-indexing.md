# ADR-0015: Revision indexing, backfill and atomic readiness

- **Status:** **M4c is accepted at review, reviewed, verified in CI and on `main` at
accepted at
the feature branch was published in Prompt
  128; The
  specification
Both main push workflows for exact commit `76fa5a3`
  passed, including the 18 PostgreSQL indexing cases, the installed-wheel embedding/indexing check
  on Ubuntu and Windows and the container indexing smoke (see
  Main CI evidence); the earlier
  feature-branch evidence at `600a366` is historical.
  The M4d specification is accepted at review; its implementation

  `3d6e8395`, not merged (ADR-0016).
  M4d–M4f implementation and overall M4 acceptance remain pending. Local Compose remains unverified.
- **Date:** 2026-10-16
- **Builds on:** [ADR-0014](0014-embedding-persistence.md) (M4b store), [ADR-0013](0013-embeddings.md)
  (M4a provider boundary), [ADR-0007](0007-durable-job-core.md) and [ADR-0008](0008-worker-runtime.md)
  (fences, runtime), [ADR-0005](0005-api-key-authentication.md) (`eg-admin`).

## Decision

M4c turns M4b's storage into a working offline indexing path. It adds enqueue and bounded backfill
seams, the `eg-admin backfill-indexes` command and the production `index_revision` handler. No
migration, dependency, lockfile, Dockerfile or Compose change was needed. Activation wiring,
recovery of terminal jobs, live providers, retrieval and M4d–M4f are not implemented.

| File | Content |
|---|---|
| `evidenceguard_persistence/indexing.py` | `enqueue_index_revision`, `backfill_index_revisions`, `load_index_target`, `pending_chunks`, `PendingChunk` |
| `evidenceguard_worker/indexing.py` | `make_index_revision_handler`, the immutable `SUPPORTED_PROVIDERS`, `page_prefix`, `stored_identity`, `resolve_provider` |
| `evidenceguard_worker/handlers.py` | Registers `index_revision` beside `ingest_revision` |
| `evidenceguard_api/admin.py` | `backfill-indexes` and `DatabaseStore` (the account store plus the backfill seam) |
| `.github/workflows/ci.yml`, `infra/ci/container_ci.py` | Registry assertions; the embedding wheel check; the indexing smoke |

## Enqueue and backfill

`enqueue_index_revision(session, actor, *, revision_id, identity)` runs in the caller's READ
COMMITTED transaction. It validates the actor (reviewer, approver or admin), the revision ID and
the storable identity before any write. It then runs M4b's `ensure_profile` and `create_index`,
and, unless the index is ready, M3a's `enqueue` with payload `{"index_id": …}` and key
`str(index.id)`, using the default 3 attempts. The outcome is `ready` (nothing enqueued),
`pending` (the job is queued or running) or `stalled` (a terminal job for a building index,
returned unchanged). It is an observation within the transaction. Creation is never inferred, and
M3a's `enqueue` is unchanged. Conflicts propagate, and the caller's transaction rolls back.

`backfill_index_revisions(session_factory, actor, *, identity, limit=50, after=None)` validates
its inputs before any transaction. It then selects up to `limit` (1–100) of the tenant's revisions
that are `active` at selection, with a chunk set and without a ready index for the profile,
ordered by revision ID after the cursor. Each selected revision is enqueued in its own
transaction. `IndexSourceNotEligibleError` becomes `ineligible`, and
`JobIdempotencyConflictError`, `EmbeddingProfileConflictError` or `IndexConflictError` becomes
`conflict`, each with a null `index_id` after that item's rollback. Any other failure propagates;
items committed earlier stay committed. `next_after` is the last selected ID when the page is full.
The supersession-race and cursor limits of the specification apply as written.

`eg-admin backfill-indexes --tenant-id T [--limit N] [--after R]` runs one page with
`HASH_IDENTITY`. It acts as the fixed system actor
`uuid5(NAMESPACE_URL, "https://evidenceguard.invalid/actors/eg-admin/v1")` with role admin for the
tenant. It prints `pending=… ready=… stalled=… ineligible=… conflict=…` and `next_after=…` only,
and exits 0 for a clean page, 3 for a page with stalled, ineligible or conflict items, 1 on failure
(fixed message) and 2 on a usage error (static message, before any database access). An invalid
`--limit` (outside 1–100, not plain digits) is a usage error.

## Handler

1. The payload must be exactly `{index_id}`, or `PermanentJobError` before any fence.
2. A short read-purpose fenced transaction (an ordinary fence holding the job lock, not `READ
   ONLY`) reads the index and its stored profile, tenant-scoped and without an index row lock.
3. `stored_identity` rebuilds the `EmbeddingIdentity` and requires its fingerprint to equal the
   stored one before any provider is resolved.
4. An already-ready index finishes through `mark_index_ready` in `ctx.fenced(finish=True)` (M4b's
   no-op with a fresh ownership check).
5. `resolve_provider` looks the fingerprint up in an immutable `MappingProxyType` copied when the
   handler is built. The production mapping holds only the offline `HASH_IDENTITY`. The provider's
   identity must equal the stored identity.
6. Each page is read in a short fenced transaction: at most 32 chunks with no embedding in this
   index, ordinal greater than the cursor, ordered by ordinal. After the fence closes:
   - the handler keeps the longest prefix within 128,000 UTF-8 bytes and verifies each text hash;
   - it calls `ctx.check()`, runs `embed_validated` and `stored_embeddings` with no transaction,
     lock or session open, then calls `ctx.check()` again;
   - it writes through `write_embeddings` in a short fenced transaction;
   - the cursor advances to the last **kept** ordinal.

   Rows committed earlier are excluded by the read, so they are reused without provider calls;
   they are not re-verified against new provider output.
7. The finish block runs `mark_index_ready` (M4b's full completeness check) and records success in
   the same transaction.

A `write_embeddings` refusal (`EmbeddingWriteRefusedError`, another attempt made the index ready)
goes to the no-op finish. If provider execution or validation fails, `ctx.check()` runs before the
failure is classified, so a latched cancellation or lease loss wins.

**Provider resolution boundary.** `resolve_provider` re-raises
`JobCancelledError`, `LeaseLostError` and `FenceClosedError` raised by the factory or the
provider's `identity` property unchanged. A `BaseException` that is not an `Exception` is never
caught. Any other failure of the factory or identity becomes the fixed `UnsupportedProfileError`,
raised outside the handler so the original exception and its text are not chained. The handler
then calls `ctx.check()` before classifying that failure as permanent, so a cancellation or lease
loss latched during the factory or identity call wins (subject to the same explicit-boundary race
as every other check).
three control-flow errors into `UnsupportedProfileError`; the reviewer reproduced this with an
isolated probe.

| Condition | Outcome |
|---|---|
| Payload, job binding or missing index | `PermanentJobError(permanent_failure)` |
| Stored-identity fingerprint mismatch, unsupported fingerprint, provider identity mismatch, an ordinary factory or identity failure (after `ctx.check()`), `EmbeddingProfileMismatchError` | `permanent_failure` |
| Text-hash mismatch, `EmbeddingSourceMismatchError`, `IndexIncompleteError` | `permanent_failure` |
| `InvalidEmbeddingError` from the provider boundary or post-rounding storage validation | `permanent_failure` |
| `EmbeddingConflictError`, `EmbeddingStorageRejectedError` | `permanent_failure`; nothing is overwritten |
| `JobLockTimeoutError` | `RetryableJobError(retryable_failure)` |
| `LeaseLostError`, `JobCancelledError`, `FenceClosedError`, anything else | Propagate (the runtime records `worker_shutdown`, nothing, or `unexpected_error`) |

**Guarantees and limits.** Checks happen at explicit boundaries only: before and after provider
work, at fence entry and after the job lock, and before success in the finish. They do not
interrupt synchronous provider or database calls, and a cancellation latched after the last check
may not stop a non-finish transaction already under way. The database fence remains
authoritative, and the accepted lease-expiry/commit window remains. Worker shutdown semantics are
unchanged. No exactly-once provider call is claimed, and an uncommitted page is recomputed on
retry. Nothing logs text, vectors, keys or exception details.

## Implementation details within the accepted contract

These are recorded for review; none changes an accepted behaviour.
1. `eg-admin` uses `DatabaseStore`, a subclass of the existing `DatabaseAdminStore` that adds
   `backfill_indexes`, so the existing account commands are unchanged.
2. The system actor ID is a fixed UUID5 literal (above). Backfill does not check that the tenant
   exists; a tenant with no eligible revisions yields an empty page and exit 0.
3. New fixed errors: `InvalidBackfillRequestError` (limit or cursor, before any transaction) in
   persistence, and `UnsupportedProfileError` and `SourceIntegrityError` in the worker. Both worker
   errors map to `permanent_failure`. A provider factory or identity property that raises an
   ordinary exception is treated as an unsupported profile; control-flow errors propagate.
4. `enqueue_index_revision` also rejects a revision ID that is not a `UUID` before any SQL.
5. `pending_chunks` re-applies the job binding and requires the passed index to be the job's own
   index in the job's tenant.
6. The container smoke expects exactly `pending=1` because its synthetic tenant has exactly one
   active revision. It compares the stored count with the index's and chunk set's `chunk_count`
   and with the count the API verified.

## CI changes

- **Registry assertions:** both kinds are now expected in `tests/test_worker_cli.py`, the CI wheel
  step and the image check.
- **Wheel step (Ubuntu and Windows):** a new isolated `python -I` script outside the checkout. It
  checks that the storage, indexing, provider and handler modules resolve to `site-packages`, runs
  `HashingEmbedder` through `embed_validated` and `stored_embeddings` (non-zero and zero rows, the
  4,100-byte wire format), checks the pinned offline fingerprint and the single-entry provider
  mapping, and checks both registry kinds. It contacts no database and does not establish indexing.
- **Container smoke:** after ingestion and the duplicate upload, and before the idle-worker stop,
  the smoke:
  - runs `eg-admin backfill-indexes` for the synthetic tenant, expecting exactly `pending=1` and
    exit 0;
  - polls, within a 90 s deadline and with per-command timeouts, a read-only `psql` session
    (`SET default_transaction_read_only = on`), with the tenant and revision UUID-validated
    before interpolation;
  - requires one index row with the same tenant and ingested revision and the pinned offline
    fingerprint, `ready`, its canonical `index_revision` job `succeeded`, and an embedding count
    equal to both `chunk_count` values and the API's verified count.

  A failed or dead job fails at once. The existing image-identity, privacy, log, first-failure,
  idle-shutdown and cleanup checks are unchanged.

## Verification

**Historical local verification.** Claude Code's local Windows results are
neither Codex nor the reviewer ran
these project checks.
separately. Both runs executed the offline `HashingEmbedder` locally, in tests and from an
isolated installed wheel. No external provider, network service, Docker or database was
contacted. At that point (before CI), the PostgreSQL tests (`tests/test_indexing_postgres.py`
and all other integration tests), Linux, the wheel step in CI and the container smoke had not
run, and all 251 integration tests, including the 18 indexing cases, were unexecuted against this
M4c version. the corrected
Those gaps were later closed for
`600a366` by the feature-branch CI evidence below. No
retrieval, semantic-quality, benchmark or production-readiness claim follows.

inspecting the implementation, corrections and supporting tests, independently matching both
export checksums and reproducing the original provider-resolution bug. Isolated standard-library
probes confirmed the same exception object in six factory/identity control-flow cases,
cancellation and lease-loss precedence over ordinary resolution failure, and a fixed ordinary
factory failure without the original exception chained. These probes do not replace project-suite,
installed-wheel, PostgreSQL or Docker execution; the reviewer ran none of those checks.
