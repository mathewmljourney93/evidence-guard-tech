# ADR-0023: Stage and call-reservation persistence

- **Status:** **M5e is reviewed, verified in CI and on main at `14f510e`**
  (main publication and exact-SHA evidence). Claude Code

the external reviewer accepted the local

  remain historical (diagnosis).

The new documentation commit's separate feature
  and main gates then passed at `14f510e`. Neither the prior failure nor the correction is a
  demonstrated production reload defect. Implements the
  accepted M5e specification, the fifth slice of the
  accepted M5 sequence.
  No application review path uses M5e and `run_review` stays unregistered; no M5e control operates
  in the application. E7 assigns output work to M5f/M5g, and overall M5 acceptance remains pending.
- **Date:** 2026-10-23 (implementation); acceptance recorded 2026-11-04
- **Builds on:** [ADR-0007](0007-durable-job-core.md) (the M3 fence and `recheck_ownership`),
  [ADR-0016](0016-snapshot-retrieval.md) (snapshot retrieval and its evidence checks),
  [ADR-0019](0019-model-call-contracts.md) (model-call values),
  [ADR-0020](0020-provenance-validation.md) (provenance values and rechecks) and
  [ADR-0022](0022-review-creation.md) (reviews, the trusted review reload and the read-boundary
  pattern).

## Decision

M5e adds a pure domain module, a persistence module, migration `0007` with four tables, and the
extracted evidence-recheck helper in the M4d retrieval module. It adds no output table or writer,
endpoint, CLI command, handler registration, provider, live call, setting or dependency.

**What it establishes.** Every planned question, its evidence, every provider-call reservation
and every committed stage of a review is stored through the caller's M3 fence, bound to the
review's canonical `run_review` job, with ownership rechecked at entry and after the last write.
At most three reservations and one repair per stage exist across job attempts; an abandoned
`started` reservation consumes budget; a committed stage is the only reusable success; identical
replay is a no-op and a differing replay a fixed conflict. A successful call and its stage are
written atomically, and an Analysis failure never alters a committed Verification. The trusted
reload rebuilds every stored value, revalidates every history and shape, and rechecks evidence
against database chunks and content with the M5b rechecks.

**What it does not establish.** Template origin of the planned questions, the original retrieval
execution, relevance or ranking, request reassembly before dispatch (a worker obligation), the
U5/U6 size assertions, or the bytes and original binding of a U4 stage's discarded evidence. It
makes no entailment, authenticity or injection-resistance claim, and no review can become
`completed` until M5f/M5g add the output slice.

## Modules and public contract

| Path | Contents |
| --- | --- |
| `packages/domain/evidenceguard_domain/review_stages.py` (new) | enumerations, `PlannedQuestionSet`, `EvidenceRecord`, `CallRejection`, `CallRecord`, `StageRecord`, `StageHistory` (V1–V12), the plan variants and `plan_stage` (T0–T9), `StageState`, `TrustedQuestionStages`, `TrustedStages`, the five canonical encodings and the bounded strict decoders |
| `packages/persistence/evidenceguard_persistence/review_stages.py` (new) | `record_planned_questions`, `read_stage_state`, `record_evidence`, `reserve_call`, `complete_failed_call`, `commit_verified`, `commit_analyzed`, `commit_unresolved`, `load_trusted_stages` and the persistence errors |
| `packages/persistence/evidenceguard_persistence/retrieval.py` (changed) | `recheck_bindings`, `load_snapshot_evidence`, `RetrievedEvidenceRow`, `EvidenceRecheckFailure` and `recheck_evidence_in_transaction`; `retrieve_with_vectors` reuses the two steps |
| `packages/persistence/evidenceguard_persistence/models.py` (changed) | `ReviewPlanQuestion`, `ReviewQuestionEvidence`, `ReviewStageCall`, `ReviewStageResult` |
| `packages/persistence/evidenceguard_persistence/migrations/versions/v0007_review_stages.py` (new) | migration `0007` (down revision `0006`) |

The successful-completion APIs take the explicit question (clarification A):
`commit_verified(fence, review_id, question_id, *, sequence, result, verified)` and
`commit_analyzed(fence, review_id, question_id, *, sequence, result, analyzed, owner)`. B3 selects
the call by `(job.tenant_id, review_id, question_id, fixed stage, sequence)`; B4 then binds the
result's question, B7 the content's identity and B8 the owner. A well-formed U4 stage has no
evidence row and no calls, reloads as valid, replays identically as a no-op after E1–E8, and
cannot be reopened by `record_evidence` (clarification B).

The domain module imports only the standard library and the domain modules `evidence`, `jobs`,
`model_calls`, `provenance` and `retrieval` (no `evidenceguard_agents`, also not lazily). The
persistence module imports the domain, `document_views`, `jobs`, `models`, `retrieval` and
SQLAlchemy. Packaging tests pin both boundaries.

## Values, state machine, persistence and reload

- **Values** follow M5e-B1: frozen dataclasses with keyword-only validating constructors, exact
  types, nested values rebuilt and required to equal the input, derived fields never accepted,
  UTC datetimes, fresh fixed errors without cause or context, and text-free representations.
  Timestamps are audit values only (V12): a call completed "before" it started is accepted.
- **Encodings** follow M5e-B2 exactly, including `float.hex()` scores, recomputed `Fraction`
  fused scores, the integer range 0…2,147,483,647 (lexical and magnitude checks) and the
  admission narrowing for inherited integers. The two maximal-size literals were derived
  independently twice in the tests (by encoding test-owned maximal dictionaries and by byte
  arithmetic without `json`): **1,135,720** and **3,090,153** bytes, matching the accepted
  values, so there is no size discrepancy.
- **State machine.** `StageHistory` enforces V1–V12; V5/V6 are checked by requiring every call to
  be what the plan of its prefix allowed. `plan_stage` is total over valid histories.
- **Persistence** follows M5e-E/F/G/H: argument checks, fence association, the ordered checks
  (E1–E8, B1–B9 or the per-API rules), replay, the mutation preconditions M1–M3, the writes and
  the final ownership recheck. The completion update is guarded by key, `started` and the current
  attempt.
- **Reload** follows M5e-J/J1 in one read-only REPEATABLE READ transaction, with M5d's
  recording wrappers so the first process-control object survives cleanup by identity.

## Implementation choices and deviations (for review)

of the local implementation commit only. At that acceptance PostgreSQL execution and exact-commit
CI were pending; the later failed feature gate is recorded below.

1. **Error placement.** The two domain errors and a common base `ReviewStageError` live in the
   domain module; the thirteen persistence errors subclass it in the persistence module (M5d put
   all its errors in the domain). Codes and meanings are as specified.
2. **Additional public names.** The domain module also exposes `StageShape` (a derived `shape`
   field on `StageRecord`), `plan_without_stage` (the plan of the calls without the committed
   stage, used for the M5e-C shape rule), `completion_shape_holds`, `CallRejection.stage_reason`
   (the M5b-F mapping), `PlannedQuestionSet.position`, the `revalidated_*` helpers used by the
   write APIs' argument checks, `dependency_canonical`/`dependency_sha256`,
   `plan_question_canonical`/`plan_question_sha256`, `encode_verified`/`encode_analyzed` and the
   three decoders.
3. **Unspecified error choices.** A verification reservation or U5 without a stored evidence row
   is `StageDependencyError` (evidence is the verification dependency); a recheck returning a job
   of another tenant and a missing review are `StageFenceMismatchError`; a fence whose `session`
   is not exactly a `FencedSession` or whose `job` is not exactly a `JobSnapshot` is an argument
   error (`InvalidStageRequestError`); an impossible stage/reason pair (`evidence_too_large` on
   analysis, `verification_unresolved` on verification) is an argument error.
4. **`commit_unresolved` precedence.** A committed stage with another outcome or reason is
   `StageConflictError` before the references are derived, because a committed success makes the
   history without its stage invalid (V9). Otherwise the derived shape decides
   (`StagePlanMismatchError`/`StageDependencyError`) and replay compares every reference.
5. **Replay and the final recheck.** The final ownership recheck also runs on a replay no-op
   (stricter than "after the last write"). `read_stage_state` writes nothing and rechecks
   ownership at entry only; it applies the E7 classification and digest checks.
6. **Unique violations.** `23505` is read from the driver diagnostics with a guarded local
   reader, because `database_failures.py` was not an authorized path; every other failure,
   including a foreign-key violation, is `StageDatabaseError`.
7. **Evidence recheck precedence.** A structurally invalid snapshot or item tuple is
   `InvalidRetrievalRequestError` (M5e-J1 step 2), whereas M4d's `check_retrieval_access` raises
   `InvalidSnapshotError` for a snapshot. `RetrievedEvidenceRow` validates its identifiers with
   the fixed M4d error, so an invalid row becomes `snapshot_inconsistent` at the same point as
   before. `load_snapshot_evidence` builds every row in the requested (fused) order before
   `_items` builds the result items; because a `RetrievedChunk` cannot fail once its evidence row
   is valid, results, outcomes and error precedence of `retrieve_with_vectors` are unchanged (the
   existing M4d tests pass unmodified).
8. **Reload details.** The reload sets `SET LOCAL statement_timeout = 30000` itself (it is the
   caller the helper's precondition names). After its rows are read, any ordinary failure while
   rebuilding them is `StageRecordInconsistentError`; the helper reports database failures as
   values (`StageDatabaseError`). It duplicates M5d's small private recording wrappers instead of
   importing private names from `reviews.py`.
9. **Schema text.** `models._sql_list` renders enumeration lists sorted, so the `IN (…)` lists in
   the constraints are alphabetical (semantically identical to the specification); the two
   `stage_reason` expressions are one check named `stage_reason`; the migration spells the
   constraint text out literally (rendered once from the models), as `0006` does.
10. **Tests.** The planner enumeration checks every one-step extension of every valid history of
    up to two calls at current attempts 1–3 (142,692 histories, 4,120 valid) against an
    independent oracle; histories with an invalid proper prefix are invalid by the same rules.
    The one PostgreSQL test that must observe a lease expiring during a real lock wait follows
    the accepted M3 precedent (a two-second lease and bounded polling).

No accepted contract was reinterpreted and no validation was weakened.

## Feature CI failure and test-setup correction

**Historical state before corrective feature CI.** M5e was published on
`feat/review-stage-persistence` at
Mathew completed the push
manually after Codex's earlier attempt stalled in Git Credential Manager and was stopped.
Four jobs passed and PostgreSQL ran but failed one test, with 384 passing integration cases.

At commit time the feature gate was
not fully green; correction-specific PostgreSQL execution and exact-version CI were pending,
and main publication was blocked. No production code, constraint, migration, model,
resource, packaging or workflow change is part of the correction.

## Limits and later-slice obligations

- No output table, value or writer exists; M5f/M5g must review the output schema and the atomic
  output-plus-job-success writer before completion is enabled (E7). No review can become
  `completed`.
- The worker composition (M5g) must prove template origin, reassemble requests from rechecked
  inputs and require their digests before every dispatch or retry, build M5c's `RepairReason`
  from stored fields with public factories, assert the U5/U6 sizes, and obtain owners from a
  trusted path.
- A U4 stage's oversized evidence bytes and their original binding assertion cannot be re-proved
  at reload; the reload proves only the well-formed U4 shape and the planned question.
- An M5e error must escape the caller's fenced block; suppressing it can commit a partial effect
  (shown by a PostgreSQL test written to document the obligation).
- Statements may run after lease expiry and are rolled back when the final recheck fails; a
  transaction that passes the final recheck just before expiry may still commit shortly after
  (the accepted M3 limit).
- The byte caps are accepted engineering limits, not measured performance or memory guarantees.
- The M4d trusted-snapshot limitation closes for review paths only once M5g obtains its snapshot
  solely through the trusted reload.
