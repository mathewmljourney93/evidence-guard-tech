# ADR-0018: Voyage embedding adapter over an injected standard-library transport

- **Status:** **Accepted at external review; reviewed, verified in CI and on `main`
  at `5acb75e5`** (`5acb75e59edbb42035d468c2c40bb0ab81a8725a`; see
  Main CI evidence at `5acb75e5`). All five required jobs passed
  for that exact commit on the feature push before the fast-forward and again on the main push.

  (feature-branch CI evidence at `84eec023`, historical);
Implements the
**Overall M4 was

  (see the acceptance assessment); the acceptance record, committed

  (publication evidence), which changes
  documentation only, so this ADR's implementation baseline stays `5acb75e5`;
  local Compose is unverified.
- **Date:** 2026-10-18
- **Builds on:** [ADR-0013](0013-embeddings.md) (M4a contracts), [ADR-0014](0014-embedding-persistence.md)
  (canonical float32 storage), [ADR-0015](0015-revision-indexing.md) (the `index_revision`
  handler and provider mapping), [ADR-0016](0016-snapshot-retrieval.md) (retrieval
  orchestration).

## Decision

M4f adds a Voyage `EmbeddingProvider` behind the existing M4a contract and a standard-library
HTTPS transport injected into it. Both are **constructed explicitly by trusted code only**:
nothing registers them, production `SUPPORTED_PROVIDERS` stays offline-only, and there is no
setting, environment variable, `.env.example` entry, CLI, endpoint, automatic indexing or live
wiring. No dependency, lockfile, migration, Dockerfile, Compose or container-smoke change.
`embed_validated` and the M4c and M4d error mappings are unchanged.

## Modules

- `evidenceguard_retrieval.voyage` (pure; standard library and `evidenceguard_domain` only):
  `VOYAGE_IDENTITY = EmbeddingIdentity("voyage", "voyage-4-lite", "voyage-http-v1", 1024, "l2")`
  (fingerprint `827fb43a08091171e8eea7b14f6943506646aff6e4dafe7e6fd47cca643cc109`, pinned in the
  tests from the literal canonical JSON); `VoyageErrorCode`, `VoyageError` (one fixed code, also
  its message and only argument, plus a derived `retryable`); `VoyageResponse` (validated
  status-and-body value); the `VoyageTransport` protocol; `build_request_body`;
  `parse_response`; and `VoyageEmbedder`. `voyage-4-lite` is a *requested* model name; no
  upstream immutability is claimed.
- `evidenceguard_worker.voyage_http`: `HttpsVoyageTransport(api_key: SecretStr, *,
  connect_timeout=10.0, io_timeout=30.0, elapsed_budget=60.0, max_response_bytes=4 MiB,
  connection_factory, clock)` over `http.client` and `ssl`; it reads no environment or file.

## Behaviour (as specified)

- **Request:** one deterministic ASCII JSON body (sorted keys, compact) with `input` as a list
  in order, the caller's `input_type`, `model`, `output_dimension` 1024, `output_dtype` `float`
  and `truncation` false. M4a's `validate_request` runs first, so an invalid request makes
  **zero** transport calls; otherwise **at most one** `post` call, with no retry, pagination
  or splitting.
- **Exchange:** `POST /v1/embeddings` on `api.voyageai.com:443` with verified TLS, fixed headers
  (`Authorization`, `Content-Type`, `Accept`, `Accept-Encoding: identity`, `User-Agent`), no
  redirect, proxy, cookie, decompression or debugging. Phases: connection and TLS, sending,
  headers, status, and for 200 only framing checks and bounded reads, then a final check.
- **Status before body:** a non-200 body is never read or drained; the transport returns a
  status-only `VoyageResponse(status, b"")`. A non-200 value carrying a body is malformed.
- **200 framing:** exactly one digit-only `Content-Length` (1–20 digits, at most the cap, else
  `voyage_response_too_large`) or a sole `chunked` `Transfer-Encoding` decoded by
  `http.client`; `Content-Encoding` absent or `identity`; anything else is malformed. Reads
  request at most 64 KiB and never more than the remaining declared length; an empty read
  before the declared length is an explicit `voyage_transport_failed` (not left to
  `IncompleteRead`, which maps to the same code); a read returning a non-`bytes` value or more
  than requested fails the same way; chunked bodies over the cap are refused after at most
  `cap + 1` decoded bytes.
- **Cooperative timing:** before each phase the remaining budget is computed and a spent
  budget means the phase is not started; the factory timeout and each `settimeout` use the
  smaller of the phase timeout and the remaining budget, through the public `connection.sock`
  only while it exists; elapsed time is rechecked after each phase and before success. A late
  non-200 status keeps its classification (N4).
- **Response validation:** the complete `VoyageResponse` is revalidated (exact type,
  reconstructed from its fields), then the status, the size, strict JSON (no `NaN` or
  `Infinity` constants, no duplicate keys), the top-level shape, the exact model echo
  `voyage-4-lite`, row cardinality and indexes (rows are placed by `index`), 1024 finite
  coordinates (huge integers are malformed), usage 0 to 2^63 − 1, and finally M4a's
  `EmbeddingBatch` (norm within 1e-6, no zero vector) as `voyage_invalid_vector`. Nothing is
  renormalized, rounded or substituted; unknown fields are parsed temporarily but not retained.
- **Errors and cleanup:** ordinary failures are classified by their own type only (never their
  chain) and raised as fresh fixed `VoyageError`s outside every handler, so public errors have
  no cause or context. The response and connection are closed separately; the first
  process-control exception that escapes into adapter-owned code is re-raised as the same
  object after cleanup; ordinary cleanup failures never change the outcome, even if their chain
  holds process control; process control from cleanup beats an ordinary operation failure.
- **Through existing boundaries:** `embed_validated` turns every `VoyageError` into M4a's
  `InvalidEmbeddingError`, so M4c records `permanent_failure` for every provider failure,
  including rate limits, timeouts and server errors (the disclosed V11 retryability gap, to be
  resolved by a separately reviewed change before any live indexing), and M4d raises
  `retrieval_provider_failed`. M5 still owns job cancellation, lease precedence and retry
  policy for retrieval orchestration.

## Implementation details for review

These are implementation choices within the accepted specification, or a pre-existing defect
fixed in an authorized path; none changes an accepted contract.

1. **Plan formatting fix.** Ruff formats Python code blocks in Markdown, and the accepted M4f
   code blocks in `docs/plan.md` at `eeef0227` were not Ruff-formatted, so
   `ruff format --check .` (a CI step) failed at that commit. `ruff format docs/plan.md`
   changed only those blocks: whitespace and line breaks, plus one trailing comma in the
   `HttpsVoyageTransport` signature. No wording, heading or anchor changed.
2. **No hidden reconnect.** `http.client` reconnects automatically when `connection.sock` is
   `None` before sending. The transport therefore requires the public socket before sending
   and before `getresponse()` (`voyage_transport_failed` otherwise) and tolerates its absence
   only after the headers, as specified.
3. **`post` argument check.** A body that is not exact `bytes` or exceeds `MAX_REQUEST_BYTES` is
   `voyage_configuration` with no connection.
4. **Header tokens.** `Transfer-Encoding` and `Content-Encoding` values are compared
   ASCII-case-insensitively after stripping spaces and tabs; a `Content-Length` value has
   surrounding spaces and tabs stripped before the digit check.
5. **Own refusals versus foreign errors.** The transport signals its own refusals with a private
   exception carrying a fixed code; a `VoyageError` raised by a connection or response object is
   foreign and, classified by its own type, becomes `voyage_transport_failed`. The adapter
   still re-raises a transport's `VoyageError` fresh with its code (as specified), unless the
   code is missing, not a `VoyageErrorCode` or raises when read, which becomes
   `voyage_transport_failed`.
6. **Construction.** `VoyageEmbedder` treats a raising `post` attribute as missing
   (`voyage_configuration`). The TLS context is created once per transport with

   inside a private error boundary (see B below). Clock results may be `int` or finite `float`.
7. **Status from the connection.** A status that is not an exact `int` from 100 to 599 is
   `voyage_malformed_response`, checked before any `VoyageResponse` is built.
8. **Public helpers and constants.** `status_code()`, `RETRYABLE_CODES`, `VOYAGE_MODEL`,
   `MAX_TEXTS` and `MAX_USAGE_TOKENS` (adapter) and `PIECE`, `MAX_SECONDS`, `MAX_KEY_LENGTH`
   and `USER_AGENT` (transport) are module-level names.
9. **Tests.** The M4d success path in the database-independent tests replaces
   `retrieve_with_vectors` with a recorder; real retrieval is the PostgreSQL case. The
   PostgreSQL module has no socket guard (the database driver's own resolution was not
   verified locally); its transport is in memory and cannot reach the network.

## Tests

- `tests/test_voyage_adapter.py`:
  pinned identity and fingerprint, exact request bytes, escaping and order, 32 texts in one
  request, every M4a request violation with zero calls, valid and reordered responses, integer
  coordinates, ignored unknown fields, 43 malformed responses (including `NaN`/`Infinity`,
  `1e400`, huge and over-long integers, duplicate keys and deep nesting), invalid and zero
  vectors, the float32 storage rejection, oversized bodies, every status mapping and
  retryability, direct-call validation of `VoyageResponse`, `parse_response` and
  `VoyageEmbedder`, transport errors and process-control identity, the unchanged
  `embed_validated` boundary, privacy with canaries, output and log capture, and mocked
  integration with the M4c handler and M4d `search_snapshot`; since

  from it, valid codes preserved fresh).
- `tests/test_voyage_http.py`:
  exact request and TLS context, the default factory constructed without connecting, adapter
  plus transport, no redirects, failures in every phase by type, status before body with
  `read()` forbidden, every framing case, explicit short-body detection, read sizes and counts,
  released-socket (`Connection: close`) success for both framings with no reconnect or private
  access, every cooperative-budget phase, reduced timeouts, configuration validation, the

  TLS-context setup failures (patched setup function; ordinary, timeout and process-control
  failures, validation first, no connection). A fake returning
  late shows only the cooperative checks, not interruption of a real socket operation.
- `tests/test_voyage_postgres.py` (2 integration cases; not run locally; both passed in
  feature-branch CI at `84eec023`):
  indexing a revision through the real handler with a mocked Voyage provider into pgvector
  (`allows_zero_vectors = false`, canonical vectors), and capture plus `search_snapshot` with
  it.
- `tests/test_packaging.py` (3 new cases): adapter and transport import boundaries, and
  unchanged production providers, registry kinds and installed commands, with no Voyage
  wiring in the API, persistence or worker outside the transport module.
- CI: one added command in the existing installed-wheel step runs the adapter with an
  in-memory fake transport and prints `Voyage adapter validated a mocked response from the
  installed wheel`.

## Limits

- **Live compatibility is unverified:** the exact model echo, the strict 200 framing, the
  normalization tolerance after float32 rounding, row order, error bodies and model
  immutability are documented uncertainties; a mismatch fails closed.
- **Timing is cooperative:** no hard wall-clock maximum. DNS, repeated connection attempts,
  TLS, header parsing and internal read loops can overrun the budget; once `getresponse()`
  releases the socket, reads keep the earlier timeout; cleanup has no deadline.
- **Process control** is preserved only where it escapes into adapter-owned code; one masked
  inside `http.client` cannot be recovered.
- **Memory:** the cap bounds accepted raw bytes only; no peak-memory figure is claimed.
- **Privacy** covers public errors, default representations, default formatted tracebacks and
  logs, not trusted code inspecting frame locals, the held key or a held response body.
- **Retryability gap (V11)** and deferred live wiring, settings and data-handling decisions
  remain; M5 snapshot obligations are unchanged.
