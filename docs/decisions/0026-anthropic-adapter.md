# ADR-0026: Anthropic adapter and HTTPS transport

- **Status:** M5h is **reviewed, verified in CI and on main** at
  `e050da3e3415d73f83db86763617d5b5f0874aeb`, within its accepted scope.
the external reviewer accepted the implementation

  Mathew manually pushed the evidence commit to the feature, all five fresh feature jobs passed,
  Codex fast-forwarded local main with `--ff-only`, and Mathew manually pushed main. All five
  separate main jobs then passed for the same exact SHA, `push`, attempt 1. This publication
it was not in that CI target. The separate
overall M5 was then
  unaccepted (historical). the
After separately
  authorized manual feature publication, it is feature-CI verified, not merged
  at `2a388dc324950d9feb46dbba3ffb75222f2a938e`. The reviewer accepted that

  local database mutation work was blocked by unavailable Docker tooling. Database-dependent
  mutations, main publication and renewed overall M5 assessment remain pending.
  accepts the blocker record and permits the same probes in existing CI PostgreSQL; the
  runner preparation

  (decision and pending exact-commit gate). The reviewer reports
  95 isolated standard-library checks; these are not PostgreSQL or CI execution. Database
  mutations subsequently executed in exact-target feature CI at `52071373` after Mathew's
  manual push: all five jobs passed, baseline/restored controls passed and A-D were caught
  with decisive retained log proofs (evidence and retention limits).

  **G1-G3 are satisfied within the accepted internal review-handler scope at `52071373`**
  (closure decision and publication gates).
  Their independent log/proof inspection and hash reconstruction was not local database
  execution. Full ephemeral records were not retrieved; retained evidence was accepted as
  sufficient. Earlier open states are historical. Completion evidence is now published on
  main and separately CI-verified at `205c987e` (actual gates);
  protected executable identities carry scoped G1-G3 closure to that version.
  accepts both exports, separate feature/main evidence, the 23-row reassessment and
  **overall M5 within the reviewed scope at implementation baseline `205c987e`**
  (distinct acceptance decision). Later documentation publication
  records that acceptance without changing executable behavior. W8, W9/M7 and W14/M6
  remain pending; this neither accepts M6/M7 nor establishes release readiness.
- **Specification:** the accepted M5h specification,

  (acceptance). The specification binds this
  implementation; nothing here changes it.
- **Preceding evidence:** M5a–M5g are reviewed, verified in CI and on main within their recorded
  scopes (M5g at `bebd2f75`, [ADR-0025](0025-review-orchestration.md)). The scoped M4d/E7
  acceptance is unchanged. That evidence is theirs; nothing below re-attributes it.

## Decision

Implement the accepted contract as specified, in two modules:

- **`evidenceguard_agents.anthropic`** (pure: standard library, the domain and M5a's
  `ModelCallTimeout`).
  - The public constants and the 19 fixed `AnthropicErrorCode` members.
  - `AnthropicError`, whose message is its code.
  - `AnthropicResponse`, with a safe representation.
  - The `AnthropicTransport` protocol.
  - `build_request_body` and `parse_response`.
  - `AnthropicProvider`, which satisfies M5a's `ModelProvider`.
- **`evidenceguard_worker.anthropic_http`.** `HttpsAnthropicTransport`, over `http.client` with
  verified TLS, a printable-ASCII `SecretStr` key and an injectable connection factory and clock.
  It imports only `evidenceguard_agents.anthropic`, the domain, `pydantic` and the standard
  library.

Nothing constructs either class outside tests. `run_review` stays unregistered, and there is no
setting, environment read, credential, endpoint or default model.

## How the contract is implemented

- **Request (M5h-C steps 1–3, M5h-D).**
  - **Revalidation.** `generate` rebuilds the request with M5a's rule (exact type,
    `dataclasses.replace`, unchanged schema and digest) and uses only the rebuilt value.
  - **Body.** The canonical, `ensure_ascii` body has exactly `max_tokens`, `messages`, `model` and
    `system`. The maximal valid request is exactly 2,784,148 bytes (tested).
  - **Calls.** An invalid request or an over-cap body makes zero transport calls; a valid dispatch
    makes exactly one.
- **Transport failures (step 4).** These are classified by their own type only:
  - process control propagates as the same object;
  - `ModelCallTimeout` and `AnthropicError(TIMEOUT)` become a fresh `ModelCallTimeout`;
  - the five kept codes are kept in a fresh error;
  - anything else is `transport_failed`.

  Errors are raised outside every handler.
- **Response admission (clarification A).** `parse_response` first requires exactly an
  `AnthropicResponse` and rebuilds it from its fields:
  - an unreadable field, a wrong type or an out-of-range status is `malformed_response`;
  - an over-cap body is `response_too_large`, whatever the status, including 504.

  Only after admission:
  - an admitted 504 becomes `ModelCallTimeout`, without JSON inspection;
  - another admitted non-200 body of 1–65,536 bytes is inspected for a strict `timeout_error`
    envelope (`type` and `error.type` only); any defect means "no envelope", and the status
    decides;
  - a 200 runs V1–V9.
- **Strict JSON (J1–J7, clarification C).**
  - **Size** is checked first.
  - **Encoding.** A leading BOM is refused, and the body must decode as strict UTF-8.
  - **Depth.** A linear pre-scan visits only quotes, backslashes and brackets, tracking strings and
    escapes, and refuses nesting deeper than 16. The recursive decoder never sees an over-deep
    input.
  - **Decoding** uses `object_pairs_hook`, which refuses duplicates at every depth;
    `parse_constant`, which refuses the named non-finite constants; a guarded `parse_float`,
    which refuses a non-finite conversion such as `1e999`, even in ignored fields; and a
    `parse_int` that refuses literals over 20 digits.
- **200 validation (V1–V9).**
  - **Envelope.** Checked for every stop reason; `id`, `stop_sequence`, `stop_details` and unknown
    fields are ignored.
  - **Other stop reasons** carry empty text, and their block payloads are not inspected.
  - **`end_turn`** needs exactly one `text` block:
    - thinking blocks are skipped;
    - citations must be absent, `null` or `[]`;
    - any other block type is malformed;
    - an escaped lone surrogate is malformed;
    - text over 65,536 UTF-8 bytes is `output_too_large`, checked last.
  - **Model echo.** `model_used` is the response `model` verbatim, so M5a's mismatch precedence
    applies only to a valid `ProviderResponse`.
- **HTTPS phases (M5h-C).**
  - **Order.** Arguments are checked first (zero clock readings and zero factory calls on a
    refusal); then the start reading; connect (then `auto_open = 0`); send and headers, each with
    the socket required; then the status, validated before the post-header elapsed check
    (clarification B).
  - **200 path.** Every later ordinary failure replaces the status: `timeout`, `clock_failed`,
    `malformed_response` (framing), `response_too_large` or `transport_failed`.
  - **Error path.** Any ordinary failure in the post-header check, the framing or the bounded
    reads, including a clock failure, yields a freshly built `AnthropicResponse(status, b"")`. The
    read cap is `min(max_response_bytes, 65,536)`.
- **Cleanup.** The response and the connection are closed separately, each at most once. Ordinary
  close failures are ignored. The first process-control object is re-raised as the same object
  after both closes; later ones are suppressed.

<a id="implementation-choices-for-review"></a>

## Remaining limitations

- **No live evidence.** The model-echo, alias, thinking and server-timeout behaviour of the real
  API is unverified. `model_mismatch` fails closed until a live run (M7).
- **No hard wall-clock bound.** DNS, several connection attempts, TLS, header parsing, internal
  read loops and cleanup can overrun the cooperative budget. No socket disposal or server-side
  cancellation is claimed.
- **Error-body loss.** When an error body cannot be read, a `timeout_error` reported under another
  status is classified as `provider_failed`.
- **Unchanged limits.**
  - no production review path or `run_review` registration;
  - U4's discarded evidence, the M3 lease/commit window and unknown outcomes;
  - no exactly-once provider call;
  - M6 approval and export;
  - the provenance-versus-semantic limits;
  - no model-quality, entailment or injection-resistance claim.
M5h is reviewed,

  its accepted scope. Overall M5 acceptance remains pending.
  Production wiring, credentials, live calls, M6 and overall M5 acceptance remain unauthorized.
