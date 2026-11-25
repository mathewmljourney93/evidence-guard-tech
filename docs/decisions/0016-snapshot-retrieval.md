# ADR-0016: Trusted snapshot capture and snapshot-relative hybrid retrieval

reviewed, verified in CI and on
  `main` at `cf2b5743`**. The earlier feature-branch verification at
  `3d6e8395` is historical.
  accepted specification. The
  push-triggered CI and secret-scan runs for exact commit `3d6e8395` passed on Ubuntu, Windows,
  PostgreSQL (all 39 M4d cases), the container job and Gitleaks (see
  Feature-branch CI evidence); this is the first
  executed PostgreSQL evidence for M4d. Claude Code's local Windows checks under
  [Verification](#verification) are historical. M4c's own evidence remains at `76fa5a3`. The M4e
  specification is accepted with its implementation pending; M4f and overall M4
  acceptance remain pending. Local Compose remains unverified.
- **Date:** 2026-10-17
- **Builds on:** [ADR-0015](0015-revision-indexing.md) (M4c indexing), [ADR-0014](0014-embedding-persistence.md)
  (M4b storage), [ADR-0013](0013-embeddings.md) (M4a provider boundary), [ADR-0011](0011-document-api.md)
  (`read_snapshot`).

## Decision

M4d adds a trusted snapshot capture seam, an immutable snapshot value, strict retrieval inputs,
the lexical and exact-vector channels, deterministic reciprocal-rank fusion (RRF), bounded results
with chunk evidence and provenance, and fixed provider and database failure boundaries. Settled
There is no migration, schema,
extension, dependency, lockfile, Dockerfile, Compose or engine-setting change, no endpoint, CLI,
worker handler or registry kind, no review persistence, report, activation wiring, stalled-index
recovery, corpus, Recall, live provider or approximate index.

| File | Content |
|---|---|
| `evidenceguard_domain/retrieval.py` | Frozen values, the `eg-retrieval-canonical-v1` encoding and digests, `query_vectors`, the pure `fuse`, fixed errors |
| `evidenceguard_persistence/retrieval.py` | `capture_snapshot`, `retrieve_with_vectors`, the statements, row conversion and the database failure boundary (`run_read`) |
| `evidenceguard_worker/retrieval.py` | `search_snapshot`, `search_current` and the provider failure boundary |
| `.github/workflows/ci.yml` | R9 only: import the three modules from the installed wheel and run `fuse` on a pinned fixture |

`evidenceguard_retrieval`, `read_snapshot` and every existing import direction are unchanged.

## Values, encoding and digests

Every value is a frozen dataclass whose constructor validates exact types (no coercion, no
`bool` for `int`, tuples only, no `str` for a `UUID`), rejects unknown keyword arguments, keeps
text verbatim and raises a fixed error outside any `except` block; `dataclasses.replace`
revalidates. Derived values (`config_sha256`; the snapshot's `profile_id`, `total_chunks` and
`sha256`; the result's tenant, vendor, digests, fingerprint and label) are computed by the
constructor and cannot be supplied. `repr`/`str` show identifiers and counts only. The canonical
encoding and both object layouts are exactly those of the specification; `captured_at` is stored
in UTC and encoded with six fractional digits. Identical encoded fields give the same digest,
different encoded timestamps can give different digests, and neither a digest nor a timestamp is
authorization, proof of past eligibility or a unique capture identifier.

## Trust model (unchanged from R3)

The seams are trusted internal programming interfaces; no endpoint calls them and no snapshot is
deserialized from untrusted input. `capture_snapshot` is the only producer of snapshots and takes
the tenant only from the trusted `ActorContext` (reviewer or approver, R4). Before every
retrieval, one statement rechecks every immutable binding (vendor, document, settled revision,
chunk set, ready index, profile) without consulting the current revision `status`, so a revision
active at capture stays eligible after supersession and a new revision never enters an older
snapshot. The recheck **cannot prove past active-at-capture eligibility**: a structurally valid
snapshot built by in-process code from a same-vendor revision superseded before capture passes
it (a PostgreSQL test documents this). M5 must persist the captured facts with review creation and
reload them only through trusted paths. No protection against malicious in-process code is
claimed. The precomputed-vector seam is trusted input: validation cannot prove that the vectors
were computed from the claimed query strings.

## Transactions and failure boundaries

Capture and retrieval each run one transaction through the unchanged `read_snapshot`: `SET
TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`, then its `SELECT clock_timestamp()`,
which establishes the snapshot, then `SET LOCAL statement_timeout = 30000` (per statement), then
the data statements. Nothing is written, enqueued or explicitly locked. Provider calls and
canonical query conversion run outside any transaction.

**Database boundary (`run_read`).** The body returns a result or a `SemanticOutcome` value; a
semantic outcome is never inferred from an exception or its chain. An inner `try` records any
ordinary body `Exception` as operational; an outer `try` records failures of session creation,
the helper's statements or cleanup. After both, outside every handler, the seam returns the result
or raises a fresh fixed error: the recorded semantic error (which stays primary if cleanup also
fails), otherwise `RetrievalDatabaseError`, also when a successful body is followed by a cleanup
failure. No original exception, statement, parameter, cause or context is kept, nothing retries
and nothing logs. `BaseException` subclasses that are not `Exception` propagate unconverted. The
session handed to the unchanged helper records any process-control exception raised by its
`execute`, `rollback` or `close`, including during the helper's two setup statements; the body
records one it raises. If an ordinary cleanup failure then replaces it, that same control
exception object is re-raised. This records process control only and never classifies semantic
outcomes.

**Provider boundary.** `search_snapshot` reads and validates `provider.identity` in its own
`try`, then calls `embed_validated` once, then converts against the snapshot identity, each with
the same outside-`except` mapping to `RetrievalProviderError`. `retrieve_with_vectors` validates
the batch again independently. No `JobContext` integration or cancellation protocol is added; M5
must define cancellation and lease precedence.

## Material implementation choices

These are routine choices within the accepted contract, recorded for review:

1. **Bindings as typed arrays.** Channel, recheck and evidence statements read the bindings from
   `unnest(CAST(:… AS uuid[]), …) AS b(…)` instead of a literal `VALUES` list: the same relation,
   constant SQL text and explicit types. Each channel statement still repeats the complete
   eligibility joins before its `LIMIT 20`.
2. **`ts_rank_cd(…, 0)`** passes the accepted normalization explicitly.
3. **Validation precedence.** The specification's summary order is applied everywhere: actor
   type, then input and structure (request, snapshot or capture inputs), then role, then scope,
   then provider or batch, then the database phase. Its step list for `retrieve_with_vectors`
   names role before structure; the summary order was chosen so that all seams agree.
4. **Error classes for result values.** `ChannelList`, `ChannelHit`, `FusedChunk`, `SourceSpan`,
   `ChunkEvidence`, `RetrievedChunk`, `RetrievalResult` and `fuse` raise
   `InvalidRetrievalRequestError` when called directly; persistence maps any such failure while
   building from rows to `SnapshotInconsistentError`. The errors share a `RetrievalError` base
   whose message is the fixed code; constructors take no arguments.
5. **Additional values.** `FusedChunk` carries a fused candidate between `fuse` and evidence
   loading. `RetrievalResult` holds its snapshot and derives the tenant, vendor and digests from it,
   so binding ownership of every item can be checked.
6. **Stricter snapshot invariants.** Excluded revision IDs must be disjoint from the bindings, and
   `revalidate_snapshot` requires the rebuilt value to equal the original, so a value altered after
   construction is rejected.
7. **Capture classification.** A stored profile whose fingerprint matches but whose fields differ
   is a consistency failure; an index ID that is not the derived ID fails when the snapshot is
   built (after the phases), as `SnapshotInconsistentError`.
8. **Row conversion.** Only fixed domain validation errors raised while constructing values from
   rows are semantic (`snapshot_inconsistent`); any other exception while reading rows is
   operational.
9. **`search_current`** checks actor type, request, vendor ID and role, then reads the provider
   identity (needed to pin the profile, protected like `search_snapshot`'s read) before capture.
10. **No evidence statement** runs when fusion yields no candidates.
11. **`STATEMENT_TIMEOUT_MS`** is a module constant read at call time; one PostgreSQL test lowers
    it locally with `monkeypatch` to provoke a timeout. The production value is not changed.

## Tests

| File | Kind | Content |
|---|---|---|
| `tests/test_retrieval_contracts.py` | database-independent | strict bounds and malformed values, independently pinned canonical bytes and digests, timestamps, invariants, `replace` revalidation, representations, query-vector conversion, fusion fixtures (ties, duplicates across queries and channels, a case where float order differs but `Fraction` ties, fewer than k, empty) |
| `tests/test_retrieval_store.py` | database-independent, fake sessions | statement order, phases and their precedence under permuted row orders, exclusions, channel SQL shape, recheck and row failures, standalone batch validation, setup/body/cleanup failure matrix, chained-semantic cases, privacy of messages, chains and tracebacks, no logging, no retry, process-control propagation including with cleanup failure;
| `tests/test_retrieval_orchestration.py` | database-independent | ordering, identity-getter failures, mismatch, identity change between reads, malformed results, provider exceptions, no session open during embedding, capture before the provider call |
| `tests/test_retrieval_postgres.py` | PostgreSQL integration | capture, exclusions and truncation, refusal cases, bounds and precedence, scope, supersession, real lexical semantics, exact cosine ordering and ties, zero vectors, end-to-end fusion, filters before limits, multiple profiles and a building index, more than 20 tempting wrong-profile and partial building-index rows, binding recheck forgeries, the documented R3 limitation, deterministic capture interleavings and a replacement activated while retrieval pauses after the recheck, timeouts, pooled settings, unchanged rows, no approximate index and evidence with a repeated header |
| `tests/test_packaging.py` | database-independent | the three modules' import boundaries |

**Lower-level fixture exception.** `_chunk_heavy_vendor`
(PostgreSQL tests) marks revisions active and indexes ready directly, with chunk sets that declare
4,096 chunks and store none, so the 100,000-chunk bound can be exercised without inserting about
100,000 chunks and vectors.
**solely for testing capture's metadata-based chunk-count arithmetic**. It may bypass ingestion
completeness and indexing readiness verification for that isolated bound test, and it proves
neither ingestion/indexing correctness nor actual stored-vector completeness. Every other
retrieval test uses the real ingestion and indexing paths. Other tests modify rows directly only
to simulate corruption (a pointer naming a superseded revision) or forge snapshots.

## Verification

## Limits

- No semantic-quality, retrieval-quality, injection-resistance, benchmark or production-readiness
  claim. The offline profile is a lexical-hash baseline, not semantic.
- Determinism is claimed only for a fixed snapshot, configuration, stored rows, PostgreSQL version
  and query vectors.
- The per-statement timeout is not a deadline for a whole capture or retrieval; the 100,000-chunk
  scan-volume figure is an engineering estimate, not a measurement.
- The trusted in-process snapshot model and its past-eligibility limitation hold until M5.
- Repeated table headers are a separate span; later citation code must not quote across the
  header/body boundary.
