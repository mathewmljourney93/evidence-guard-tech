# ADR-0025: Review orchestration and atomic output

- **Status:** M5g is **reviewed, verified in CI and on main at `bebd2f75`** within its
  accepted scope (main publication). Feature and main exact-commit CI passed;

  (reviewer logs). Earlier it was feature-CI verified at `3d41f435`
  (evidence), which is now historical. The sequence
  was:

    (external review).
    run for it.

    cross-question test comparison
    (f0d4ce92 evidence and correction).

    (review); feature CI for `3d41f435`
    then passed all five required jobs. Claude Code saw conclusions only; the reviewer later

feature CI, the `--ff-only` main
    fast-forward, the manual main push and main CI all passed (main publication).

    evidence accepted (reviewer logs); an M4d/E7 closure assessment and a
    proposed M5h specification added for review, neither accepted.

    `bebd2f75`; M5h left proposed, with its contracts completed (disposition).

    A–C (record); its implementation is pending.

  M5h implementation, M6 and overall M5 acceptance are pending, and production wiring is not
  authorized. Statements below that M5g is staged,
  unaccepted, unexecuted or blocked describe the state at the time and are historical.
- **Specification:** accepted M5g specification,
  G1–G15 and G17–G24 with binding clarifications A and B
  (acceptance); G16 not selected.
  Implementation status.
- **Preceding evidence:** M5a–M5f are reviewed, verified in CI and on main within their recorded
  scopes ([ADR-0024](0024-review-report-content.md) for M5f at `e7dd3be3`). That evidence is
  theirs; nothing below re-attributes it.

## Decision

Four new modules implement the accepted contract; no M5a–M5f production module, migration
`0001`–`0007`, dependency, setting, endpoint, command or production registration changes.

| Module | Owns |
| --- | --- |
| `evidenceguard_domain.review_outputs` | `ReviewOutput`, `StoredReviewOutput`, `ReviewOutputWrite`, `ReviewStatus`, `decode_stored_review_output`, two fixed errors |
| `evidenceguard_persistence.review_outputs` | `write_review_output`, `load_review_output`, `load_review_status`, eight fixed errors |
| `migrations/versions/v0008_review_outputs.py` | migration `0008` |
| `evidenceguard_worker.review` | `make_run_review_handler`, `REVIEW_WORKER_ACTOR_ID`, `MAX_ITERATIONS`, `TrustedReviewOutput`, `load_trusted_review_output`, worker errors, the orchestration |

Two existing production files change, both within the accepted scope:
`models.py` (the `review_outputs` metadata and `uq_reviews_tenant_id_id_run_review_job_id`) and
`db.py` (the G15 `transaction()` rule only).

**`run_review` remains unregistered.** `production_registry()` still claims only
`ingest_revision` and `index_revision`. Only test registries build the handler, and the factory
has no default model provider.

## How the contract is implemented

- **Values (M5g-A).** Frozen dataclasses with keyword-only constructors guarded by one fixed
  error each. A missing keyword is detected through a private sentinel default, so it is the
  value's fixed error rather than Python's `TypeError`. Types are exact; nested content is
  rebuilt with `revalidate_review_report` and every derived field is recomputed (derived fields
  cannot be passed). `created_at` is converted to UTC. Representations carry identifiers,
  digests and counts only.
- **Decoder.** Closed key set, exact column types and patterns, the printable-ASCII and size
  checks before decoding, the strict M5f decode against the stored digest, the rebuild, then
  every derived column.
- **Migration `0008`.** It first adds the `reviews` unique, then creates `review_outputs` with
  the 17 named checks, the primary key, the `(tenant_id, job_id)` unique and three `NO ACTION`
  foreign keys. Downgrade drops exactly the table, then that unique.
- **Writer (F2).** Arguments (with `JobSnapshot` and `ReviewOutput` rebuilt), fence
  association with an entry ownership recheck, binding, completeness, replay or conflict,
  insert with `job_attempt` from the fence and `created_at` by `RETURNING`, final ownership
  recheck. It never commits, rolls back, closes, retries or logs.
- **Reads (F2, F4, G3).** The actor is rebuilt and the review ID type-checked before the role
  check, and both before any session is opened. One `read_snapshot` transaction with recording
  wrappers; the missing-review and non-canonical-job checks; then one shared lifecycle/presence
  function for both loaders. `load_trusted_review_output` inherits all of it, then renders and
  compares (F3). Drift raises `ReviewRendererDriftError` and repairs nothing.
- **Orchestration (B–D).** Pure job and payload checks, the fixed actor, the M5d loader, the M5c
  planner, one fenced `record_planned_questions`, the M5e trusted reload, then each question in
  order: the Verification loop (bound 5) and the owner-only Analysis loop (bound 4) driven only
  by `plan_stage`. Requests are reconstructed exactly as in C3, with the repair reason always
  built from the call numbered `trigger`. Completion runs a second reload, the M5f build and its
  source-bound recheck, the pinned render, then `write_review_output` inside
  `ctx.fenced(finish=True)`.
- **Failures (E, E2, H).** Guarded steps keep only the failure class, run `ctx.check()` and then
  raise a fresh job error. Fenced writes classify only an escaping object that **is** the body's
  own fixed error, after leaving the context and after `ctx.check()`. Every other ordinary
  context-exit failure becomes `ReviewFenceExitError`, with no `ctx.check()` on that branch.
  Control flow and process control are never caught or converted.

## Material implementation choices

These resolve details the specification left to the implementation. None changes accepted
behaviour; each was a review question.

1. **Unrecognized step failures.** The precedence rule's "fixed guarded-call error" is a new
   internal `ReviewStepError` (code `review_step_failed`). Like `ReviewFenceExitError` it is
   privacy normalization only: the runtime records `unexpected_error` (retryable). Known classes
   map as in M5g-H.
2. **`StageCallInFlightError`** (which `reserve_call` can raise and the H table does not list)
   is a retryable body classification, consistent with G6's treatment of `PlanInFlight`.
3. **Reload checks.** Each trusted reload must cover the planned questions in order and name
   this job (otherwise permanent), and its `job_attempt` must equal the attempt being run
   (otherwise the same retryable composition error as `PlanInFlight`: the state is not this
   attempt's).
4. **A committed S1 seen mid-attempt.** C4 returns `PlanReuse` stages. G4 requires the owner to
   come from the reload or this attempt's `verify_question`. An S1 that appears after the entry
   reload without a trusted owner value (possible only out-of-band) is therefore the retryable
   composition error, so the next attempt reloads it.
5. **`ctx.check()` after every guarded step**, pure steps included. This is more boundaries than
   the minimum list in M5g-E, never fewer, and it never runs on a process-control or uncertain
   context-exit path.
6. **Replay and the final check.** An identical-row replay still runs the final ownership
   recheck (read-only) before returning `replayed=True`.
7. **Completeness by shape.** The writer and the reader derive a stored stage row's shape from
   its outcome and reason (the M5e-C rule) and compare it with the wrapper's `ReportStage`
   together with the outcome, reason and four digests.
8. **Read statement timeout.** The reads set the transaction-local 30-second statement timeout
   used by the M5e reload. This bounds statements, not the read.
9. **Names.** The ORM class is `ReviewOutputRow`, to avoid colliding with the domain value. The
   private composition error has a retryable subclass rather than an instance flag, so that
   classification stays by class.
10. **`TrustedReviewOutput`** verifies the Markdown digest and size itself. An invalid
    construction is `InvalidStoredOutputError`; the loader reports any render or comparison
    failure as `ReviewRendererDriftError`.

## G15: the narrow `transaction()` change

The helper now applies the E3 rule. Across the body, `commit()`, `rollback()` and `close()`, the
first `BaseException` that is not an `Exception` is raised as the same object, and later
failures are dropped uninspected. Without process control, the ordinary object selected is the
one the previous helper selected. Once a session exists, `commit()` runs at most once,
`rollback()` at most once and `close()` exactly once. A failing `session_factory()` makes no
lifecycle call and its exception propagates unchanged (clarification B).

Nothing is logged, retried or inspected, and no rollback, disposal or commit outcome is claimed.
G16's public uncertain-finish property is not added.

- `tests/test_transaction_process_control.py` checks all 625 phase combinations against an
  independent E3 oracle (identity and call counts).
- The same module checks 16 ordinary-only combinations against a verbatim copy of the published
  helper (same object, same calls) and session-construction failure for an ordinary error and
  each process-control type.
- It also checks that `GeneratorExit` thrown at the yield comes back as the same object, and
  pins the published helper's loss of identity.
- The existing non-database transaction, job, fence, runtime, ingest, index, API, M5d and M5e
  tests all pass unchanged in the full run.
- Their PostgreSQL counterparts were **not executed** here.

## Output atomicity, lifecycle reads and runtime uncertainty

The output row and the job's `succeeded` transition are written in one finish transaction. The
fake-session tests drive the real `transaction()`, `JobContext` and `run_worker` and cover these
cases:

- **A commit that raised before taking effect:** neither the output nor the success exists.
- **A commit that took effect but raised, or a `close()` failure after it:** both exist. The
  finish is `UNCERTAIN`, the handler raises `ReviewFenceExitError`, and the runtime's
  `fail_retryable` is refused, so `job.outcome_unknown` is logged.

Outcome-write failures are read back, never inferred from `job.outcome_failed` (clarification A):

- a failure before `COMMIT` leaves the job `running`;
- a raising commit that did not apply leaves it `running`;
- an acknowledged commit followed by a raising `close()` leaves it `succeeded`.

No runtime behaviour changed.

## Evidence attribution and verification limits

codes and hashes are in the handoff):

- Ruff format and lint, and strict mypy.
- The focused M5g modules, and the full suite with skip reasons.
- Integration and non-integration collection.
- Baseline and candidate builds with a member comparison.
- The complete installed-wheel CI step in a fresh environment outside the checkout.

**Not established:**

- **PostgreSQL behaviour.** `test_review_outputs_postgres.py`, `test_review_handler_postgres.py`
  and `test_review_canary_postgres.py`, and every existing PostgreSQL test, were skipped: no
  `EG_TEST_DATABASE_URL`. The constraint, writer, read and end-to-end database behaviour is
  therefore unverified. `alembic check` against PostgreSQL was not run.
- **CI and review.** No CI ran and nothing is reviewed or accepted.
- **The installed-wheel assertion** imports the modules, refuses a provider-less factory and
  renders `0008` offline. It is not PostgreSQL execution.
- **Model behaviour.** The canary tests use scripted outputs. Passing them does not establish
  live-model injection resistance, and there is no production denylist.

## Remaining limitations

composition at `bebd2f75` (disposition). The M4d and
the other limits stand.

- **No live provider and no production review path.** `run_review` is unregistered; no endpoint,
  command, setting or enqueue path exists. M5h, M6 and overall M5 acceptance are pending.
- **M4d trusted-snapshot limitation.** The mechanisms that could close it for the `run_review`
  path now exist:
  - the handler's only retrieval is `search_snapshot` over the M5d-loaded snapshot, enforced by
    a structure test;
  - nothing recaptures the snapshot.

  It is **not closed**: the replacement-activation PostgreSQL test has not run, and the
  implementation is unreviewed. Outside that claim stay `search_current` callers, direct
  database writes, malicious in-process code, original retrieval membership and rank beyond
  M5e-J1, and the U4 discarded bytes.
- **E7 (output scope).** The output table and atomic writer now exist in code and their offline
  shape is tested. Their database behaviour is unverified, so E7 is not claimed satisfied.
- **The lease window.** It is unchanged: a fenced transaction that passed its last check may
  commit shortly after the lease expires.
- **Fixed limits:** no overall review deadline (G7) and no exactly-once provider call.
- **Uncertain finishes stay unreadable** to the handler, by design (G11, G16 not selected).

## Feature CI at `f0d4ce92` and the abandoned-reservation test correction

**Publication.**

- **What was pushed:** after the preparation commit
  `f0d4ce921a4e58ce381d3f3d26e9a0a80ad94b2c` (README and threat-model status corrections),
  Mathew pushed it manually as the new branch `feat/review-orchestration`. Main was unchanged at
  `e7dd3be3`.
- **What Claude Code could see:** using anonymous API access it observed only run, job and step
  conclusions. The integration job failed at "Run integration tests" and the other four required
  jobs succeeded.
- **Access limitation (historical):** its job-log download returned HTTP 403, so it recorded no
  counts or test names.

**Logs retrieved by the external reviewer (the reviewer's observations, not Claude Code's).** All
were from commit `f0d4ce92`, branch `feat/review-orchestration`, the push event, attempt 1.

- [ci run 42205208269](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269):
  - [verify (ubuntu-24.04)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986602):
    `4999 passed, 439 skipped in 128.52s`.
  - [verify (windows-2025)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986480):
    `4998 passed, 440 skipped in 183.71s`.
  - Both verify logs printed `production registry: ingest_revision, index_revision` and all
    twelve installed-wheel result lines, including "review orchestration imported and migration
    0008 rendered offline from the installed wheel".
  - [integration (PostgreSQL 17 + pgvector)](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986506):
    `1 failed, 438 passed, 4999 deselected in 345.13s`, with 439 of 5438 collected tests
    selected.
  - [container](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208269/job/127849986032):
    the smoke and cleanup succeeded.
- [secret-scan run 42205208210](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208210):
  [Gitleaks](https://github.com/mathewmljourney93/evidenceguard-agentic-rag/actions/runs/42205208210/job/127849986119)
  scanned 96 commits and found no leaks.

**What those passes do not show:**

- The container smoke exercises the existing ingestion and indexing path, not M5g review
  orchestration.
- The wheel's Recall line is arithmetic and its Voyage line mocked.
- The offline `0008` SQL rendering is not database execution.

Claude Code holds no copy of the reviewer's log archive.

**Diagnosis (the reviewer's).** The one failure was
`tests/test_review_handler_postgres.py::test_a_reservation_abandoned_before_dispatch_is_retried_on_the_next_attempt`,
at its final assertion:

- **The flaw:** the final query selected every Verification call across all questions, ordered
  them by `question_id` and `sequence`, and compared the first retry with the first row. The
  pinned template begins with `RET-01`, but alphabetical order puts `BCP-01` first, so the
  assertion compared request digests of **different questions**.
- **What did pass:** the log shows the earlier assertions passing. The cancellation raised
  `JobCancelledError`, one sequence-1 started reservation from attempt 1 remained, the next
  worker run exited successfully, and the job reached `succeeded`.
- **Conclusion:** the failure is an invalid test comparison, not a demonstrated production retry
  defect.

**Correction.**

- **Before the retry:** the test captures the single interrupted reservation and requires its
  complete identity: tenant, review, job, the first **planned** question (template order),
  `verification`, sequence 1, `initial`/`original`, `started` and job attempt 1. It records that
  row's request digest.
- **After the retry:** it queries only that tenant, review, question and stage, ordered by
  sequence. It requires exactly sequence 1 (`initial`/`original`, still `started`, attempt 1)
  and sequence 2 (`retry`/`original`, `completed`, attempt 2), and both digests must equal the
  captured digest. The `succeeded` job assertion is kept.
- **No-dispatch proof:** the cancelling provider now records every call, and the test asserts
  zero. Raising inside `generate` alone proved nothing, because `call_validated` maps an ordinary
  provider exception to `provider_failed`.
- **Unchanged:** no hardcoded digest, template-order, planner, retry-rule or production change.

**Status.**

- **Database execution:** for `f0d4ce92`, PostgreSQL has now executed and the gate failed (one
  test). The corrected test is collected but **not executed locally**: no disposable test
  database is configured.
- **Scope of the passing jobs:** they are evidence for `f0d4ce92` only, not for the correction.

- **Blocked:** feature CI is not verified, and main publication remains blocked until CI passes
  on the corrected version.
- **Not claimed:** M4d and E7 are not declared closed, and M5h, M6 and overall M5 acceptance
  remain pending.
