# ADR-0019: Model-call contracts, the validating call boundary and the scripted fake

feature CI evidence
on `main` at `f04e0957`, verified in
  feature-branch and main-push CI for that exact commit** (see
  Feature-branch CI evidence and
  Main publication evidence). The

  at `46c02257`, publication authorized but not yet run); that wording is historical.

  External review). Implements the
  accepted M5a specification, the first slice of the
  accepted M5 sequence.
- **Date:** 2026-10-19
- **Builds on:** [ADR-0003](0003-plain-python-workflow.md) (plain-Python workflow),
  [ADR-0016](0016-snapshot-retrieval.md) (the value and fixed-error style reused here) and
  [ADR-0018](0018-voyage-adapter.md) (the explicit-construction, mocked-provider precedent).

## Decision

M5a adds the values every later M5 slice uses to ask a model for a structured judgment and to
classify what came back, one shared validating call boundary, and a deterministic, test-owned
scripted provider. It is pure: no database, migration, network, credentials, settings, prompts,
provenance checks, orchestration, `JobContext` or handler registration, and no change to any
M1–M4 contract. Nothing constructs a provider in production.

## Modules

| Module | Contents | Imports |
|---|---|---|
| `evidenceguard_domain.model_calls` | `ModelPurpose`, `PromptRef`, `ModelUsage`, `StopKind`, `CallOutcome`, `StructuredRequest`, `ProviderResponse`, `StructuredResult`, bounds, the canonical request encoding and the fixed errors | standard library; `agent_outputs` locally (below) |
| `evidenceguard_domain.agent_outputs` | `QuoteRef`, `ClaimOutput`, `VerifierOutput`, `FindingOutput`, `AnalystOutput`, the closed schema registry and `parse_output` | standard library, Pydantic, `evidence`, `model_calls` |
| `evidenceguard_agents.providers` | `ModelProvider`, `ModelCallTimeout`, `call_validated` | standard library, domain |
| `evidenceguard_agents.scripted` | `ScriptedFakeProvider`, its steps and `CallRecord` | standard library, domain, `providers` |

`evidenceguard_agents` is a new import package (wheel, sdist and strict mypy). Packaging tests
forbid it from importing persistence, retrieval, the apps or SQLAlchemy; they forbid every other
package from importing it; and they restrict the M5a modules to the standard library and the domain
(plus Pydantic in `agent_outputs`) with no `socket`, `ssl`, `http`, `urllib`, `os`, `pathlib`,
`tomllib` or `io`. These are architectural checks against accidental access, not a sandbox against
malicious trusted Python code.

**Dependency arrangement.** `agent_outputs` imports `model_calls` at module level (for
`ModelPurpose`, the schema identifiers, `utf8_size` and `InvalidModelValueError`). `StructuredResult`
needs the output classes only to check an `output` value, so it imports `agent_outputs` **inside**
that check (`_check_output`). There is no cycle at module load, and `model_calls` stays importable
without Pydantic. `model_calls` repeats the `QuestionId` pattern rather than importing the
Pydantic-based `evidence` module; a test pins the two patterns as equal.

## Behaviour (as specified)

- **Call values** are frozen dataclasses with exact-type validation (no coercion, no `bool` for
  `int`), unknown keywords rejected, no stripping, derived fields (`output_schema`,
  `request_sha256`) computed by the constructor, and revalidation through `dataclasses.replace`.
  Nested `PromptRef` and `ModelUsage` values are rebuilt, so a bypassed nested value is caught.
- **`StructuredResult`** validates every field and accepts only the five rows of the accepted table:
  output only for `completed`; `model_used` and `usage` together, only for a received valid
  response (equal to the requested model except for `model_mismatch`); nothing for `timeout`;
  `provider_failed` with latency only when dispatched. A supplied output is revalidated.
- **Canonical encoding** `eg-model-call-canonical-v1`: sorted keys, compact separators, ASCII,
  `allow_nan=False`; texts enter only as SHA-256 of their UTF-8 bytes; `timeout_ms` is excluded.
  The digest is pinned in tests against independently computed bytes. It identifies request
  content for reuse and audit; it is not authorization or proof of a call or of any past state.
- **Output schemas** are strict, frozen, non-stripping Pydantic models with `extra="forbid"`,
  `revalidate_instances="always"` and `hide_input_in_errors=True`. Every collection is a tuple;
  attribute assignment and deletion raise `InvalidModelValueError`. Quote references use the
  canonical lowercase hyphenated UUID spelling (a pattern, so other spellings are rejected, never
  normalized) with a `chunk_uuid` property; exact duplicate quote references within one claim or
  finding and duplicate finding question IDs are rejected; text rejects NUL and lone surrogates.
- **Parsing** is two-pass: at most 65,536 UTF-8 bytes; a `json.loads` scan with a duplicate-key
  hook, non-finite constant and number rejection, a JSON-object top level and an iterative walk
  bounding depth to 8 and the value count to 2,000; then strict **JSON-mode** validation of the same
  text. Every failure gives `None` (`invalid_output`).
- **Validation-error privacy:** `__init__`, `model_validate`, `model_validate_json`,
  `model_validate_strings` and `model_copy` run each whole operation (input traversal, reading the
  update mapping, copying and validation) inside one boundary that turns any ordinary failure into
  a fresh `InvalidModelValueError` raised after the handler (no cause, context or original text),
  and accept no extra options (strictness cannot be switched off per call).
  `model_validate_strings` is the same strict Python-mode validation as `model_validate`. `repr`, `str` and `__repr_args__` show the
  type name and counts only, for every nested type.
- **`call_validated`** follows the accepted order: revalidate the request (rebuilt and compared on
  `output_schema` and `request_sha256`) and require a callable clock, else
  `InvalidModelRequestError`; an unusable start reading raises `ModelClockError`; `provider_id`
  must be exactly a `str` matching `^[a-z][a-z0-9-]{0,31}$`, else `provider_failed` without
  dispatch; one `generate` call (`ModelCallTimeout` → `timeout`, any other ordinary exception →
  `provider_failed`); the end reading; response and nested usage revalidation (else
  `provider_failed` without accounting fields); then model mismatch, refusal, `max_tokens`, other
  stop and strict parsing, in that precedence. No retry, no repair. Only `Exception` is caught;
  process control from the clock, `provider_id` or `generate` propagates as the same object.
- **Clock:** a reading is usable only if it is exactly an `int` within ±2**53 (checked with integer
  comparisons before conversion, so `10**1000` never reaches `float` or `math.isfinite`) or exactly
  a finite `float` within the same bound. After dispatch, an unusable end reading, backwards time, a
  latency above 86,400,000 ms or any ordinary failure while calculating leaves `latency_ms` absent
  and keeps the outcome; a latency is never clamped or invented.
- **Scripted fake:** `Respond`, `Refuse`, `StopMaxTokens`, `StopOther`, `Timeout`, `Fail` and
  `WrongModel` steps keyed by `(prompt_id, question_id)`; at most 256 keys, 16 steps per key,
  65,536 bytes per text and 4 MiB of script text in total, copied into immutable tuples. Under one
  lock each call takes its key's next step and appends a `CallRecord` (identifiers, request digest
  and step index only; capped at 4,096); the step runs outside the lock. A missing key, an exhausted
  script (the last step is never repeated) or a full history raises the fixed `ScriptedFakeError`
  without recording. Reading the supplied configuration mapping is inside the same kind of error
  boundary. Scripts hold raw text for a test-owned lifetime; representations show the
  model ID and counts only.

## Implementation choices and deviations (approved at review)

1. **Pydantic base-init flag.** To translate validation errors, the output base overrides
   `__init__`. Pydantic 2.14 treats any `__init__` that lacks the `__pydantic_base_init__` flag as a
   custom initializer and, during `model_validate_json`, calls it with the raw decoded values; strict
   Python-mode validation then rejected valid JSON enum strings (observed locally with the locked
   Pydantic 2.14.0 while implementing). The override only wraps `BaseModel.__init__`, so it carries
   the same flag Pydantic sets on its own `__init__`. This relies on a Pydantic source-level
   convention: `test_pydantic_treats_the_wrapping_init_as_its_own` pins
   `__pydantic_custom_init__ is False` for every output type, and the JSON-mode parsing tests fail
   if the convention changes.
2. **Nested-instance rule at the Python-mode entry points.** Strict Python mode accepts a `dict` for
   a nested model field (observed locally). The accepted contract requires nested model instances
   in direct construction, so `__init__`, `model_validate` and `model_validate_strings` reject a
   nested tuple field whose items are not exact instances. A schema-level `before` validator was
   tried first and rejected: in JSON mode it hands the decoded list to strict tuple validation as a
   Python value, which then fails. JSON-mode validation is therefore unaffected.
3. **`WrongModel` must name a different model.** The fake's constructor rejects a `WrongModel` step
   whose `model_used` equals the fake's own model ID, since such a step would not exercise a
   mismatch. This narrows the accepted step definition for fixtures only.
4. **The revalidated request is dispatched.** `call_validated` passes the rebuilt request (equal in
   every field and digest) to `generate`, not the caller's object.
5. **Ruff first-party list.** `pyproject.toml` also adds `evidenceguard_agents` to Ruff's
   `known-first-party`, alongside the other import packages, so imports sort correctly. It relaxes no
   rule; it is outside the literal "packaging and mypy lists" wording and is flagged for review.
6. **Model-validation options.** The public validators accept no keyword options (for example
   `strict=False` or `from_attributes=True` raise `InvalidModelValueError`), so strictness cannot be
   weakened per call.

## Limits

- **No production use:** nothing registers, configures or networks a provider; the scripted fake
  is a contract fixture, never quality evidence. Provenance checks, prompts, request assembly,
  persisted snapshots and orchestration are later slices; the M4d trusted-snapshot limitation is
  unchanged.
- **Timing:** `timeout_ms` is passed to adapters; `call_validated` imposes no hard deadline and
  cannot interrupt a blocking provider. Latency is descriptive.
- **Privacy** covers public errors, default representations and logs. It does not cover trusted
  code inspecting frame locals or held values, `model_dump` and attribute access (which return
  content by design), or bypasses such as `model_construct` and `object.__setattr__`.
- **Pydantic coupling:** choice 1 relies on a Pydantic source convention, pinned by tests.
- Bounds are engineering defaults, not measured limits.
- **Verification scope:** M5a changes neither the container smoke (offline ingestion, indexing and
  idle-worker shutdown only) nor its scope; local Compose remains unverified. No semantic-quality,
  injection-resistance or production-readiness guarantee is made.
