# ADR-0013: Embedding contracts and deterministic offline hashing

- **Status:** Accepted. Verified and on `main` at `5fdaa1c` (fast-forward of
  `feat/embedding-contracts`; see main CI evidence).
  Earlier feature-branch verification at `d501bd6` is retained as historical.
  Linux/Windows verification, CI builds and existing clean installed-wheel checks
  passed; direct isolated installed-wheel embedding-provider execution remains
  unverified.
  implementation is pending. M4c–M4f and overall M4 acceptance remain pending.
- **Date:** 2026-10-16
- **Builds on:** the accepted M4a specification in the plan
  and [ADR-0010](0010-document-ingestion.md). M3 ingestion and activation are unchanged.

## Contracts and boundaries

`evidenceguard_domain.embeddings` defines frozen, closed `EmbeddingIdentity`,
`EmbeddingUsage` and `EmbeddingBatch` dataclasses. This follows the existing
chunk-value pattern. Constructors validate strict types without coercion;
`dataclasses.replace` is the supported copy/revalidation path. Unknown fields
are rejected. Collections are tuples and nested values are frozen contracts.
As with other Python domain values, privileged `object.__setattr__` can bypass
immutability; this is not a sandbox. Provider output is revalidated even when
it already has the expected Python class.

Identity has exactly `provider_id`, `model_id`, `algorithm_version`, `dims` and
`normalization`. Identifiers match `[a-z][a-z0-9._-]{0,63}`; dimensions are strict
integers 1–4096; normalization is `l2`. The fingerprint hashes ASCII JSON with
these five keys, sorted keys, compact separators and no NaN, using SHA-256.
The offline identity is `offline` / `fake-hash-v1` / `ascii-word-sha256-v1` /
1024 / `l2`. Feature, algorithm, dimension or normalization changes require a
new identity/version. This is distinct from upstream API model-version guarantees.

`evidenceguard_retrieval.embeddings` defines `EmbeddingProvider` with a read-only
identity property and `embed(texts, input_type) -> EmbeddingBatch`, plus the
frozen `HashingEmbedder`. `embed_validated` validates the request, captures and
validates the requested identity before calling the provider, then reconstructs
and checks the returned batch against identity, mode and input count. It rejects
malformed nested values, wrong vector shape/types/norm, zero-policy violations
and malformed usage. Raw provider exceptions are replaced by the fixed
`InvalidEmbeddingError` (`invalid_embedding`) outside the exception handler,
without retaining the provider exception as context. Representations omit text,
vector contents, submitted identity strings and usage counts.

## Input and numeric validation

Inputs are tuples of 1–32 strings, each 1–4,000 code points and at most 16,000
strict UTF-8 bytes, nonblank under `str.isspace`, without NUL or lone surrogates.
The aggregate limit is 128,000 UTF-8 bytes. The per-input byte limit is also
implied by 4,000 code points in strict UTF-8; it is checked explicitly. Input
strings pass unchanged: no stripping, Unicode normalization or truncation.
Mode is strictly `query` or `document`. Duplicates retain their positions.

Coordinates are strict int/float values, excluding booleans, in immutable tuples.
They must be finite; nonzero vectors have L2 norm within absolute tolerance 1e-6
of one. `math.hypot` validates the norm without squared-coordinate overflow or
underflow. Extreme integer conversion failures become the same fixed error,
with no raw conversion exception attached. Zero vectors are allowed only for
the offline provider and must be excluded from future cosine candidates. A live
provider zero vector is rejected. Usage is a nonnegative strict integer token
count, or `None` when unknown; hashing always returns `None`, never a fabricated
billable token count.

## Exact hashing algorithm

1. Extract maximal ASCII `[A-Za-z0-9]+` runs and lowercase their ASCII letters.
   Other characters delimit tokens; no stemming or stopword filtering occurs.
2. Emit `u:` plus each token, and `b:` plus each adjacent token pair joined by
   one ASCII space. Count every occurrence, including repetition.
3. SHA-256 each UTF-8 feature. Interpret the first eight digest bytes as an
   unsigned big-endian integer modulo 1024 for the bucket. Digest byte 8 even
   gives +1; odd gives -1. Sum signed integer counts by bucket.
4. Divide coordinates by the square root of the sum of squared counts in bucket
   order; a zero norm gives 1024 zero coordinates. No built-in `hash`, random
   seed, environment read, network, downloaded model or SDK is used.

All offline output is labelled **lexical-hash baseline - not semantic**.
Query/document vectors share the algorithm but retain their requested mode.
Literal fingerprint and bucket/sign fixtures are calculated independently of
the implementation. Tests cover repetition, opposite-sign collisions and
cancellation, Unicode/no-feature zeros, cross-process hash-seed independence,
bounds, strict types, copying, malicious provider outputs and privacy.

## Verification and limits

PostgreSQL skips and one POSIX-only signal skip; 126 focused embedding/packaging
checks passed) are recorded in the
plan. The earlier local build
attempt used offline mode with build isolation disabled and failed because the
local environment lacked `hatchling`; no dependency was installed. This remains
historical local evidence, not a current CI build failure. Later CI builds and
existing installed-wheel checks passed for `d501bd6` and again on `main` at
`5fdaa1c`, as recorded above; direct
embedding-provider execution from an isolated installed wheel remains unverified.
Local Compose remains unverified; the container smoke is CI-only evidence.

This slice adds no persistence, migration, pgvector, indexing job, worker
registration, live adapter, corpus evaluation, ranking or review workflow.
It demonstrates deterministic lexical contracts, not semantic quality or an
end-to-end prompt-injection defence. M4b–M4f remain unimplemented. The M4b
persistence specification was
accepted at review in the plan

M4c–M4f still require their own detailed specification reviews. No benchmark or production-readiness
claim follows.
