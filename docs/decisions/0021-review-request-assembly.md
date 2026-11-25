# ADR-0021: Review template, Planner, prompts and request assembly

  184 for a local implementation commit only** (see
  External review); **reviewed, verified in
see
  Main publication evidence; the final
  history commit changes prompts.md only; job-log results independently retrieved by the external

  verification and current-version CI were pending. No application path, handler, endpoint, setting or production
  registry uses M5c, so none of its controls operates in the application, and overall M5
  acceptance is pending. Implements the
  accepted M5c specification, the third slice of the
  accepted M5 sequence.
- **Date:** 2026-10-21
- **Builds on:** [ADR-0019](0019-model-call-contracts.md) (`StructuredRequest`, `PromptRef`,
  `parse_output` and the scripted fake) and [ADR-0020](0020-provenance-validation.md)
  (`QuestionEvidence`, `VerifiedQuestion`, `ProvenanceRejection` and quote matching).

## Decision

M5c adds five modules and three packaged data files to `evidenceguard_agents`: fixed errors, a
packaged digest-pinned review template with a pure parser and pinned loaders, a deterministic
Planner, two versioned system prompts with pinned loaders, and request assembly that serializes
every untrusted string only inside JSON string values of a closed schema, binds the system text
to the pinned prompt digest, refuses oversize requests and builds repair requests by reassembly.
It adds no persistence, migration, review handler, endpoint, setting, production registry entry,
live provider, network code or dependency, and changes no M1–M5b contract or behaviour.

**What it establishes.** Structural safety of the request format (document text cannot end a
JSON string value or create a field), deterministic bytes and request digests, exact
template and prompt identity for artifacts loaded through the pinned loaders, and refusal instead
of truncation. **What it does not.** It does not make a live model injection-resistant (a model
can still follow persuasive document text; measured in M7), does not guarantee that a model
encodes a quotation correctly (a wrongly encoded one fails the existing M5a/M5b checks), cannot
prove that its evidence or Verifier inputs came from trusted paths (M5g's obligation), makes no
peak-memory or hard-deadline guarantee, and does not enforce the lifetime repair or call budget
(M5g). A request digest identifies content and configuration, not tenant authorization or review
identity.

## Modules, data and public contract

| File | Contents |
|---|---|
| `artifact_errors.py` | `ReviewArtifactError` and the nine fixed errors; `run_guarded` and `require` |
| `templates.py` | `TemplateRef`, `ReviewTemplate`, `parse_template`, `load_template`, `load_pinned_template`, the template registry |
| `planner.py` | `PlannedQuestion`, `plan_review` |
| `prompts.py` | `PromptSpec`, `load_prompt`, `load_pinned_prompt`, the prompt registry and the binding check |
| `assembly.py` | `VERIFIER_INPUT_FORMAT`, `ANALYST_INPUT_FORMAT`, `ModelSettings`, `VerifierRequestInputs`, `AnalystRequestInputs`, `RepairReason`, `assemble_verifier_request`, `assemble_analyst_request`, `assemble_repair_request` |
| `data/templates/vendor_security_review_v1.toml` | the accepted first template |
| `data/prompts/verifier/v1.md`, `data/prompts/risk_analyst/v1.md` | the v1 system prompts |

**Pinned artifacts** (SHA-256 of the exact file bytes; UTF-8 without BOM, LF, ASCII only):

| Artifact | Bytes | SHA-256 |
|---|---|---|
| `vendor_security_review` v1 (template) | 1,969 | `26fcbe26dcc47f5991da5b741475c736cec27b1f2bd6ab515ec07ac59895786a` |
| `verifier` v1 (purpose `verifier`) | 4,213 | `629f8f972a0f5d6247a54364da59f04d53a1a023472fa00830ebedfe106b007d` |
| `risk_analyst` v1 (purpose `risk_analyst`) | 4,002 | `f8e485998dc2ff79c839100c27326a6e119135788060237a9fcbe5fed0051b29` |

The template holds exactly the accepted M5c-C2 table (eight questions, IDs and texts shared with
the evaluation questions, separately authored queries in the accepted order, explicit
documentary flags) under the title "Vendor security review", with a two-line comment header. The

task, the input format and the exact output schema, "Respond with one JSON object only", the
untrusted-data statements (every `evidence` string; for the Analyst every
`verification.rationale`, `claims[].text` and `citations[].quote`), chunk-ID and exact-quote
rules, single standard JSON escaping of quotes, `insufficient_evidence`, and no canary list or
injection claim.
(`supported` for an answer the cited passages give, affirmative or negative; `contradicted` only
for conflicting cited passages with at least two distinct quotations; `insufficient_evidence`
when the evidence does not answer), both prompts say that EvidenceGuard checks quote provenance
only, and both describe the optional `repair` member. **Their exact wording and bytes are part of
this implementation review.**

- **Values** are frozen dataclasses with validating keyword-only constructors (exact types,
  `bool` never an `int`, tuples only, unknown keywords rejected). Nested values are rebuilt
  through their own constructors (`PromptRef`, `RetrievalRequest`, `QuestionEvidence`, `VerifiedQuestion`,
  `ProvenanceRejection` and the M5c values), so `model_construct` and `object.__setattr__`
  bypasses are revalidated. A nested `EvidenceQuestion` in either stage's inputs is checked at
  the M5c boundary **before** any reconstruction (exact `str` ID and text, an exact `tuple` of
  exact `str` queries, an exact `bool` flag), then rebuilt with `EvidenceQuestion.model_validate`
  and required to be unchanged in value and type. `dataclasses.replace` runs the
  same constructor. Representations
  show identifiers, versions, purposes, digests and counts only.
- **Template rules.** The template-string rule (exact `str`, strict UTF-8, no NUL, equal to its
  own `str.strip()`, bounded) applies identically to the title, question texts and queries; the
  template-question rule additionally requires the built `EvidenceQuestion` to equal the
  supplied fields exactly. `parse_template` takes exactly `bytes` (at most 65,536, no BOM, strict
  UTF-8, `tomllib`, closed keys at every level) and returns the SHA-256 of exactly those bytes.
- **Trusted loading.** `load_template` maps wrong argument shapes to `InvalidAgentArgumentError`,
  an unregistered pair to `UnknownTemplateError`, and a missing, unreadable, oversize, altered or
  invalid resource or a registry-key mismatch to `TemplateIntegrityError`.
  `load_pinned_template(ref)` additionally requires the complete loaded reference to equal `ref`.
  `load_prompt`/`load_pinned_prompt` do the same for prompts (`UnknownPromptError`,
  `PromptIntegrityError`; empty, BOM, NUL, non-UTF-8 and oversize bytes are each refused) and
  return the exact decoded text. A directly constructed `ReviewTemplate` never proves packaged
  origin; trusted paths use only the pinned loaders.
- **Bounded reads.** Resources are opened in binary mode through `importlib.resources.files` by
  fixed registered names and read with repeated `read(n)` calls. Each request is bounded by the
  remaining allowance (the limit plus one byte minus the bytes already received); short reads are
  continued; reading stops at end of file or once more than the limit has been received, so under
  the reader contract no more than the limit plus one byte is received. An oversize resource is
  refused. The file is never read whole and then measured.
- **Planner.** `plan_review(template, *, k=8)` returns one `PlannedQuestion` per question in
  template order with `RetrievalRequest(question.search_queries, k)`; `PlannedQuestion` requires
  the request's queries to equal the question's search queries exactly. No expansion or model
  call.
- **Prompt binding (M5c-E1).** Before serialization each assembler rebuilds the `PromptSpec` and
  settings, requires the function's purpose, a registered `(prompt_id, version)` of that purpose
  whose pinned digest equals the reference digest, and a 1–64,000-byte strict UTF-8 system text
  without NUL whose SHA-256 equals that digest. `StructuredRequest` is not relied on for this.
- **Assembly.** The closed `eg-verifier-input-v1` and `eg-analyst-input-v1` objects of M5c-F1 and
  F2 are built from rebuilt inputs (header and body separate, rank order, only validated
  citations, claims and rationale for the Analyst; no tenant, review, snapshot, revision or
  document ID or `document_key`), every string is checked for strict UTF-8 encodability
  (`InvalidAssemblyInputError` otherwise), and the object is serialized with
  `json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
  allow_nan=False)`. A user text above 400,000 UTF-8 bytes, all metadata included, is
  `RequestTooLargeError` before any `StructuredRequest` exists; nothing is truncated. Replies are
  validated by M5a's unchanged two-pass `parse_output`; nothing decodes returned quotations again.
- **Repair (M5c-F5).** `assemble_repair_request(original, inputs, reason)` rebuilds all three,
  checks purpose and question, reassembles the unrepaired request from `inputs` and requires it
  to equal `original` in every field (so an already-repaired request is rejected), then adds
  `"repair":{"citation_index":…,"item_index":…,"reason":…}` and keeps every other field.
  `RepairReason` accepts `invalid_output` (no positions, either purpose) or an M5b
  `RejectionReason` under exactly the `ProvenanceRejection` stage and position rules.
- **Errors and process control.** Each public operation runs as one guarded operation: ordinary
  failures become a fresh fixed error (code as message) raised after the handler with no cause or
  context; process control propagates as the same object. Nothing logs.

## Implementation choices and deviations

Routine choices within the accepted contract:

1. **Error base and runner.** A `ReviewArtifactError` base class; `run_guarded(build, error,
   keep=…)` re-raises a kept M5c error class as a fresh instance of that class and maps every
   other ordinary failure to `error`. `artifact_errors.py` imports `collections.abc` and `typing`
   for these signatures (M5c-B lists no imports for this file).
2. **Shared private helpers.** `prompts` uses `templates._read_packaged`; `planner` uses
   `templates._rebuilt_template` and `_template_question`; `assembly` uses `prompts._is_bound` and
   `_rebuilt_spec`. The registries are private module dictionaries.
3. **Identifier checks without `re`.** The template-ID pattern is checked character by character
   so `templates.py` stays within its accepted standard-library list; question IDs use the
   existing `is_question_id`.
4. **`RepairReason` positions** are validated by constructing an M5b `ProvenanceRejection` with
   `rejected_count` 1 (valid for every reason), so the rules cannot drift from M5b.
5.
   (exact field types, revalidation, unchanged values), not the template-question rule.
6. **Defaults** `DEFAULT_MAX_OUTPUT_TOKENS = 4_096` (C6) and the M5a `DEFAULT_TIMEOUT_MS`.

Implementation choices **approved at review**:

1. **Existing packaging test narrowed.** `test_m5b_is_not_wired_into_any_application_or_handler`
   asserted that no agents module mentions `provenance`. M5c-B places the import of
   `evidenceguard_domain.provenance` in `assembly.py`, so the test now exempts exactly that file;
   every other check is unchanged. The agents file-set test now lists the accepted M5c modules
   and `data/` directory.
2. **Bounded-read strategy.** Each request is bounded by the remaining allowance and no more
   than the limit plus one byte is accumulated. The earlier specification and docstring wording
   (the total *requested* never exceeds the limit plus one byte) did not hold for the sum of
the strategy itself is unchanged.
   The tests pin the per-request bound and that an oversize resource stops after exactly the
   limit plus one byte.
3. **Ground-truth separation test scope.** The test that the template copies no answer-bearing
   label compares anchors, gold and forbidden lists, acceptable claims and quotes, but excludes
   epoch names and `expected_status` values, because the status value `documentary_support` is
   also part of the template's own key `requires_documentary_support`. This is a limited check
   alongside the separately reviewed template table, not a universal proof against evaluation
   contamination.

No dependency, lockfile or `pyproject.toml` change was needed: the wheel and sdist include the
data files without an explicit include (build comparison below).

## Limits and later-slice obligations

- Structural encoding only; no semantic injection resistance, live quality or prompt-quality
  claim. The canary acceptance fixture, negative control and authorized-quotation limitation
  probe remain M5g's; M5c tests only that the injected trust-center paragraph sits inside exactly
  one evidence string value.
- M5d stores the `TemplateRef`, both `PromptRef`s, the model settings and the tenant, review and
  snapshot bindings; M5e keys stored calls and outputs by request digest within those bindings;
  M5g loads artifacts only through `load_pinned_template` and `load_pinned_prompt`, supplies only
  trusted evidence and Verifier values, enforces the repair and call budget and runs the canary
  fixtures; M7 measures live behaviour.
- Published template and prompt files are immutable; any change is a new version file with a new
  pinned digest.
