# ADR-0017: Synthetic corpus, anchor-to-chunk ground truth and retrieval evaluation

**reviewed, verified in CI
  and on `main` at `0ae4c6ca`** (`0ae4c6ca339232e40cc007d7b78334af08a8b25b`; see
  Main CI evidence at `0ae4c6ca`). Feature-branch CI passed
  for that exact commit before the fast-forward, and main CI then passed. Claude Code

OpenAI Codex handled the subsequent documentation, commits and publication in
Implements the
  accepted M4e specification.
  The feature-branch evidence at `d1dcdfce` and
  the failed Ubuntu run and passing PostgreSQL results at `c14821b7`
  (historical evidence)
  remain historical. Recall is report-only with no threshold; no numerical database-derived
  corpus Recall value is supplied. M4f and overall M4 acceptance remain pending; local Compose
  is unverified.
- **Date:** 2026-10-17
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (M4d snapshot capture and retrieval),
  [ADR-0015](0015-revision-indexing.md) (M4c indexing), [ADR-0010](0010-document-ingestion.md)
  (the `text-md-v1` chunker), [ADR-0011](0011-document-api.md) (`create_upload`, `read_snapshot`).

## Decision

M4e adds a fictional evaluation corpus with hand-authored ground truth, pure code that validates
it, maps anchors to stored chunks and computes exact Recall@5 and Recall@8, and a test-only
worker module that loads the corpus through the production lifecycle, verifies a loaded database
read-only and runs the production M4d retrieval for two epochs. The results are **reported, never
gated on a Recall threshold**; the evaluation fails only on contract or isolation failures. Every
report carries the stamp "NOT a quality measurement of semantic retrieval": the offline hashing
profile is a lexical baseline, not a semantic one.

There is no migration, schema, dependency, lockfile, Dockerfile, Compose, container-smoke,
registry or handler change, no endpoint and **no installed command** (`eg-eval` does not exist).
The PostgreSQL tests are the only callers of the orchestrator, always through the existing guarded
disposable-database fixtures, which are unchanged.

## Layout

- `sample_data/`: `corpus.toml` (`eg-corpus-v1`), `documents/<tenant>/<vendor>/<key>@r<n>.md`,
  `variants/injected/...` (one replaced document) and `ground_truth/<tenant>.toml`
  (`eg-ground-truth-v1`). Two demo tenants (Halverson Freight, Marisol Clinics), three fictional
  vendors, 12 revisions, 17 anchors and 10 questions. It ships in the sdist, not the wheel.
- `evidenceguard_retrieval.evaluation` (pure; standard library, domain and retrieval only, no
  `os`, file, database or network access): `corpus` (schemas, bounds, references, quote rules,
  variant check, file-set check), `anchors` (exact location, chunk mapping, `parts`, manifest
  verification) and `recall` (exact `Fraction` Recall, digest, contract and isolation checks,
  canonical report).
- `evidenceguard_worker.evaluation` (test-only): the file reader, `run_fresh_two_epoch`,
  `verify_loaded` and `evaluate`.

## Corpus and ground truth

References are always qualified, `tenant/vendor/document@rN#anchor`; bare anchor names are never
accepted, so the same local name in two tenants or revisions is unambiguous. Each question has one
or more cases, each naming the epochs (`initial`, `final`) it applies to; gold must name the
revision eligible in that epoch (r1 for `initial`, the document's latest for `final`), belong to
the question's own tenant and vendor, and be disjoint from `forbidden`. Forbidden references may
cross tenants; foreign-tenant forbidden anchors provide the canaries. Quotes follow N11 exactly
(type, 1–4,000 code points, strict UTF-8, no CR or controls except TAB and LF, no leading or
trailing whitespace, multiline allowed, no normalization; non-overlapping left-to-right
`occurrence`). The injected variant must equal its clean document with exactly one paragraph
inserted. Unknown keys and out-of-bound values are rejected before any database work.

The reader refuses symlinks at every path component, non-regular files, unexpected files under
`documents/`, `variants/` or `ground_truth/`, and files over their byte bound (checked before and
after reading). The corpus digest `eg-corpus-digest-v1` hashes the variant name and the effective
file set (paths sorted by UTF-8 bytes), each field framed by an 8-byte big-endian length.

## Orchestration (three contracts)

1. `run_fresh_two_epoch` first re-derives and completely validates the suite, then refuses any existing corpus-tenant vendor, document, revision, profile,
   index or corpus job (`corpus_state_not_fresh`), accepting an empty or a seeded-only database;
   then seeds, creates vendors, uploads, ingests and indexes every r1, captures and **retains** the
   `initial` snapshots while no later revision exists, applies later revisions in manifest order
   and captures `final`. Job outcomes come from the rows, never from worker exit codes; each job
   allows at most two single-claim worker runs. `stop_after` is the test hook for partial states.
2. `verify_loaded` runs entirely in one `read_snapshot` transaction (REPEATABLE READ, READ ONLY),
   compares every corpus-tenant record with the corpus, enumerates every embedding profile of
   each corpus tenant and returns only the logical-to-actual ID map. It writes, captures and
   repairs nothing, and never produces an `initial` epoch.
3. `evaluate` reads stored chunks of every loaded revision, verifies each manifest against the
   rebuilt and offline manifests, resolves every anchor against the stored spans, and runs
   `search_snapshot` (k = 8; Recall@5 uses the first five) for every retained snapshot.

## Reports, errors and determinism

- **Question outcomes.** `ok` (Recall@5 and Recall@8 as exact fractions), `ok_empty_gold` (valid,
  Recall `null`, excluded from the macro) and `invalid` (any contract or isolation failure; Recall
  `null`). Any invalid question fails its group, whose macro values are then both `null`, and
  fails the report; `require_passing` raises `evaluation_failed` whatever the Recall elsewhere.
  Recall is never gated on a threshold.
- **Observed output is kept.** The report lists each question's ranked chunk IDs as returned,
  duplicates and forbidden results included, with the owning logical reference or an explicit
  `null` for a chunk outside the loaded corpus. Failure entries name the code, tenant, vendor,
  epoch, question and, where applicable, the chunk ID and position.
- **Privacy.** Errors and reports carry fixed codes, logical references, IDs, counts and
  fractions only: never document text, quotes, evidence text or raw exception content.
  Operational failures (loading, capture, retrieval) raise a fixed `EvaluationError` and produce
  no report.
- **Encoding.** Canonical JSON (sorted keys, compact separators, ASCII), groups sorted by tenant,
  vendor and epoch, questions by ID; fractions as numerator, denominator and a round-half-even
  four-decimal display.
- **Determinism limits.** Production UUIDs, timestamps and tie-breaking are unchanged. The same
  retained snapshots give byte-identical reports; two fresh databases are compared only
  structurally (logical references, group shapes, gold counts), never by IDs, digests, tied ranks
  or Recall.

## Material implementation choices

- **Failure conversion.** `_guard` keeps an own `EvaluationError`, maps an M4d `RetrievalError` to
  `retrieval_failed` with its fixed code as `detail`, and maps any other `Exception` to the step's
  fixed code, raising outside the handler so no message, cause or context is retained.
  `BaseException` process control propagates unconverted.
- **Vendors.** `ensure_vendor` lists, creates, and on `DuplicateVendorSlugError` re-reads; a stored
  name that differs from the manifest is `corpus_conflict`.
- **Capture check.** Each capture must bind exactly the expected epoch revisions
  (`corpus_capture_mismatch`); evaluation additionally requires gold within the snapshot's chunks
  (`gold_not_in_snapshot`) and every snapshot to share one profile and configuration.
- **Canaries** are the quotes of the case's forbidden anchors in other tenants; a returned chunk
  whose evidence text contains one is `foreign_canary`. The two Marisol canary strings
  (`LV-TB-CANARY-36H`, `LV-TB-CANARY-AES`) are authored isolation content of the fictional
  documents; no marker is inserted into any document to support anchor mapping.
- **Resetting within a test.** Two PostgreSQL tests need a second clean database within one test
  (two fresh loads; an extra-profile fresh-run refusal). They reset the already validated
  disposable database exactly as the shared `empty_database` and `migrated` fixtures do; the
  fixtures and guards themselves are unchanged.
- **Verifier reads.** Revision rows are read in one statement including `content_text`, which is
  compared exactly with the corpus text. Job `payload` is not read: the accepted checks compare
  each canonical job's kind, idempotency key and status only. This omission from the accepted

  scope; no payload validation is claimed and the read list is not redefined.

## Tests

- Database-independent: `tests/test_evaluation_corpus.py` (committed corpus, schemas, bounds,
  references, epoch cases, quote and occurrence rules, `parts`, documents, variant, file sets and
  reader safety including symlinks), `tests/test_evaluation_anchors.py` (exact location without
  normalization, body and header routes, `parts` outcomes, a synthetic long table with repeated
  headers, manifest verification) and `tests/test_evaluation_recall.py` (the 2/3 example, Recall
  and macro cases, display rounding, digest framing, contract and isolation classification, group
  counts and failed groups, `require_passing`, canonical and private reports).
- PostgreSQL (`tests/test_evaluation_postgres.py`, 16 integration cases): the fresh run and both
  epochs, evaluation, repeatability and the k = 5 prefix; verifier success with no writes (row
  comparison and recorded statements); refusals for empty, seeded-only, every stopped phase,
  conflicting metadata and content, an extra document and an extra profile; fresh-run refusal of
  every partial state; production-seam reuse; the injected variant; two structurally equal loads.

  validation before any session-factory call, the `_read` process-control, refusal, ordinary
  and cleanup matrix and the three read entry points, vendor creation with transaction
  doubles, and instrumented reader bounds) and `validate_suite` cases in
  `tests/test_evaluation_anchors.py` (missing, ambiguous and out-of-range quotes, a quote
  crossing a boundary without `parts`, invalid `parts`, forbidden-only and unused anchors,
  the selected variant's text, both committed variants and a tampered suite).

  and ordinary failures from the setup clock result's `scalar_one()`, through `_read` and the
  three read entry points, plus a successful result path through the proxy.
- `tests/test_packaging.py`: the evaluation modules' import boundaries, the worker module's
  boundaries and the absence of an `eg-eval` command.
- CI (E9): one installed-wheel step importing the three pure modules from `site-packages` and
  computing the 2/3 example.

## Exact-commit CI at `c14821b7` and test correction

**Publication.** Claude Code published `feat/retrieval-evaluation` at
`c14821b72d82f3a174123011b4d2c002fdcadbf3` (a history-only commit on top of the accepted
implementation commit `f01af7eb`). The push-triggered
[ci run](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984)
(attempt 1) **failed**; the secret-scan run succeeded. Claude Code observed only GitHub API
conclusions (its anonymous log downloads returned HTTP 403): Ubuntu verify failed at its `Test`
step, with the build and installed-wheel steps skipped; Windows verify, PostgreSQL integration,
the container job (all six steps) and full-history Gitleaks succeeded.

**Evidence retrieved independently by the external reviewer** (connected GitHub log retrieval;
not observed by Claude Code):

- [Ubuntu verify](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984/job/117451164827):
  `1 failed, 2245 passed, 306 skipped in 23.00s`. The failure is
  `tests/test_evaluation_worker.py::test_a_file_larger_than_its_reported_size_fails_within_its_bound`,
  asserting at line 598: expected `corpus_file_changed`, received `corpus_read_failed`.
  Formatting, lint and type checks passed; the build and installed-wheel steps were skipped.
- [PostgreSQL integration](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/39051603984/job/117451164752):
  `306 passed, 2246 deselected in 212.64s`; the log shows all 16 tests in
  `tests/test_evaluation_postgres.py` passing. This is the first executed PostgreSQL evidence for
  M4e. The logs supply no numerical Recall result, and none is claimed.
- No additional counts or output were supplied for the Windows, container or secret-scan jobs.

**Diagnosis (external reviewer).** The test replaced `os.lstat` with a double that called
`Path(path).resolve()` to identify its target. On Linux, `Path.resolve()` itself calls
`os.lstat`, so the double re-entered itself (by Claude Code's reading of the reader, the
resulting ordinary `RecursionError` is what its guard converts to the private
`corpus_read_failed`). The reviewer reproduced the recursion with a
standalone standard-library probe on Linux. This is a defect in the test double; no production
defect has been established. On Windows, `Path.resolve()` does not call `os.lstat`, which is why
the test passed there.

**Correction.** The double now
identifies its target with a purely lexical key (`os.path.normcase(os.path.abspath(...))`),
computed for the target before the patch is installed, so it performs no file-system operation
that could re-enter the patched function. It keeps every `st_*` field of the real result and
reports the target's size 10 bytes smaller, so the reader's bounded read still observes
`corpus_file_changed`. A new assertion requires that the understated result was actually
returned for the target, so the test cannot pass without exercising the intended condition. The
production reader, its validation and its error codes are unchanged, and the test is not skipped
on any platform. The other file-system doubles in the file (`os.open`, `Path.read_bytes`,
`os.fdopen`) use only lexical path operations and were left unchanged.

**Historical verification.** Run locally on Windows by Claude Code (locked environment, offline;
no Docker, database or external provider contact):

- the corrected test passed, and `tests/test_evaluation_worker.py`: 99 passed;
- `ruff format --check .` (171 files) and `ruff check .`: clean; strict `mypy` (135 source
  files): no issues;
- full suite: 2244 passed, 308 skipped (306 integration tests without a database, the symlink
  test and the POSIX-only signal test);
- a standalone standard-library probe on Windows, calling `posixpath.realpath` (the function
  `Path.resolve()` uses on POSIX), reproduced the recursion with the old double's pattern and
  showed the new lexical key making no `os.lstat` call. This is a stand-in, not Linux execution.

build and installed-wheel steps were pending. These gaps were subsequently closed for
`d1dcdfce` by the feature-branch CI evidence above; the Windows results here remain historical.

## Limits

- Recall from the offline hashing profile measures lexical overlap on a tiny fictional corpus; it
  is not a semantic-quality, benchmark or production result, and no threshold is applied.
- Isolation checks cover the returned chunks and the corpus's canaries only; they do not prove
  tenant isolation in general. End-to-end canary and output behaviour remain M5/M7, and the
  injected variant makes no injection-resistance claim.
- The orchestrator trusts its caller to pass a guarded disposable database; it has no production
  entry point.
