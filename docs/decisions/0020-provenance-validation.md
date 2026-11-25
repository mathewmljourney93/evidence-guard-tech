# ADR-0020: Provenance validation, quote matching and status derivation

reviewed, verified in feature-branch and main-push
  CI for the exact commit and on `main` at `90295717`** (see
  External review and
  Main publication evidence, whose job-log
the
  acceptance commit itself records the pre-publication state, which is historical). Overall M5
  acceptance is pending; no review path uses M5b yet. Implements the
  accepted M5b specification, the second
  slice of the
  accepted M5 sequence.
  Implementation review, Linux verification and current-version CI are pending.
- **Date:** 2026-10-20
- **Builds on:** [ADR-0016](0016-snapshot-retrieval.md) (`ChunkEvidence`, `RetrievalResult` and
  the value style) and [ADR-0019](0019-model-call-contracts.md) (`StructuredResult` and the strict
  Verifier and Risk Analyst output schemas).

## Decision

M5b adds one pure module, `evidenceguard_domain.provenance`, that turns a completed Verifier result
and the trusted retrieval evidence for one question into a `Verification` with derived status and
trusted citation metadata, restricts Risk Analyst findings to citations the Verifier already
validated, revalidates both on reload, and derives the deterministic documentary-support finding.
It has no persistence, migration, prompt, request assembly, orchestration, endpoint, setting,
provider call or production wiring, and changes no M1–M4 or M5a contract.

**What it proves.** An accepted citation proves **provenance only**: the stored quote is an exact,
contiguous substring of one span (header or body) of a chunk in the retrieval result supplied for
that question, with exact chunk-text and source offsets, and its tenant, revision, document,
source type and authenticity come from that trusted evidence. It does **not** prove semantic
entailment (whether the passage supports the claim; a model judgment measured in M7), document
authenticity (always `not_established`), or that the supplied retrieval result was really
retrieved for this review and question (M5d/M5g supply it from trusted paths). It makes no
injection-resistance claim: a genuine authorized quotation containing injected text is accepted.

## Module and public contract

`packages/domain/evidenceguard_domain/provenance.py` imports only the standard library
(`unicodedata`, `uuid`, `dataclasses`, `enum`, `contextlib`, `re`, `collections.abc`, `typing`)
and the domain modules `evidence`, `retrieval`, `model_calls`, `agent_outputs` and `chunks`. The
packaging tests pin this list and forbid network, file, environment, logging and direct Pydantic
imports, and check that no other package mentions the module (no wiring).

Public names, as specified (M5b-B): `MATCH_RULES` (`eg-quote-match-v1`), `QuoteSpanKind`,
`FindingKind`, `RejectionStage`, `RejectionReason`, the values `QuoteMatch`, `QuestionEvidence`,
`AcceptedCitation`, `ValidatedClaim`, `VerifiedQuestion`, `AnalyzedQuestion` and
`ProvenanceRejection`, the functions `match_quote`, `derive_status`, `verify_question`,
`recheck_verified`, `analyze_question`, `recheck_analyzed`, `documentary_gap_finding` and
`finding_id`, and the errors `InvalidProvenanceInputError` (`invalid_provenance_input`) and
`InvalidProvenanceValueError` (`invalid_provenance_value`).

- **Values** are frozen dataclasses with keyword-only constructors that check exact types (`bool`
  is not an `int`, tuples only, no `str` for a `UUID`), reject unknown keywords, rebuild every
  nested value through its constructor (`Citation`, `Verification`, `Finding` and
  `EvidenceQuestion` through `model_copy()`; `ChunkEvidence`, `RetrievalResult`,
  `StructuredResult` and the M5b values through their constructors) and enforce every
  constructor invariant of M5b-B1. `dataclasses.replace` revalidates. Representations show IDs,
  reasons, offsets, counts and digests only.
- **Quote matching** follows M5b-C exactly (segment-wise NFD, whitespace units, initial
  non-starter run as one segment, independent header and body spans, unit-boundary occurrences,
  first occurrence with no fallback, the 64-occurrence cap, the 1,000-code-point original bound,
  the edge-whitespace check, exact offset mapping). Span forms are computed at most once per chunk
  within one `verify_question` call.
- **Verifier conversion** binds the trusted `QuestionEvidence` and a revalidated completed
  Verifier `StructuredResult` for the same question, then runs the three phases of M5b-D with the
  M5b-F precedence and counts, deduplicates citations by `(chunk_id, original quote)` with
  canonical claim indexes, enforces P7 and the status table, and builds the `Verification`.
- **Analysis** checks owner, question, result and shared identities before examining any
  finding (M5b-E1), checks every finding, resolves each quote reference by whole-quote equivalence
  to an owner citation, requires every listed shared `Verification` to hold the **same full
  citation value**, enforces common verdicts, derives each
  finding's status from its own trusted citations, keeps follow-up questions verbatim and assigns
  deterministic IDs. A rejection never modifies the owner.
- **Reload.** `recheck_verified` rebuilds the value and evidence, requires matching identities and
  trusted metadata and recomputes `match_quote` from the trusted `ChunkEvidence` and the stored
  original quote, requiring a `QuoteMatch` equal in every field. `recheck_analyzed` rebuilds all
  inputs, checks the outer identities first (also for an empty analysis), then for every finding
  checks its scope, resolves each stored citation by `(chunk_id, quote)` to the trusted owner
  citation and requires **full `Citation` equality** (tenant, revision, chunk, source type, quote,
  authenticity) with it and with every listed shared Verification's citation,
  re-derives the status from those trusted citations, and checks verdicts and IDs. Analyst and
  Verifier request digests are never compared.
- **Documentary rule (P11).** `documentary_gap_finding` checks the question identity first, then
  returns the fixed rule finding (ID `finding_id(…, documentary_support_required, 0)`, title
  "Documentary evidence required", the fixed statement, severity `medium`, status `missing`, the
  Verification's vendor citations) for a `vendor_claim` on a question requiring documentary
  support, otherwise `None`. **M5f and M5g must include it in the hash-covered report whenever
  its condition holds, even if analysis fails**; this module does not persist or render reports.
- **Errors and process control.** Every public operation runs as one guarded operation:
  ordinary exceptions (including nested `InvalidRetrievalRequestError`, `InvalidModelValueError`
  and Pydantic errors) become a fresh fixed error raised after the handler, with no cause or
  context; exception chains are never inspected; process control (`KeyboardInterrupt`,
  `SystemExit`, `GeneratorExit`) propagates as the same object. Model-caused failures never raise.
  Nothing logs.

## Implementation choices and deviations

Routine choices (resolved within the accepted contract):

1. **Internal-inconsistency signalling.** A private marker exception lets the shared guard report
   an unreachable failure while building the derived `Verification`, `AcceptedCitation`,
   `VerifiedQuestion`, `Finding` or `AnalyzedQuestion` as `InvalidProvenanceValueError`, while
   every other function failure is `InvalidProvenanceInputError` (pinned by a test that forces the
   `Verification` constructor to fail).
2. **Citation construction failure.** If building the `Citation` for an accepted original raised
   (not reachable for valid evidence), the reference is rejected as `quote_not_exact`, the same
   reason as a failed round-trip equality, rather than escaping as an error.
3. **Analyst quote resolution.** A reference resolves to the first owner citation with the same
   chunk ID and the same M5b-C quote form; for values produced by `verify_question` or accepted
   by `recheck_verified` that mapping is unique. A blank quote form never resolves
   (`citation_not_validated`).
4. **Bounds as named constants** (`MAX_QUOTE_CHARS`, `MAX_OCCURRENCES`, `MAX_SHARED_QUESTIONS` and
   others), the documentary-rule text as constants, and a `ProvenanceError` base class for the two
   fixed errors.

Implementation choices **approved at review**:

1. **`chunks` import.** The specification lists `evidence`, `retrieval`, `model_calls` and
   `agent_outputs`; the module also imports `evidenceguard_domain.chunks` for the existing
   4,000-code-point chunk bound (`MAX_CHUNK_CHARS`) instead of repeating the literal.
2. **`ProvenanceRejection.provenance_check`.** A read-only property returning the §4 value from
   the M5b-F table (`citation_rejected` for the reference, claim-coverage and the two citation
   reasons, otherwise `invalid_output`), so M5e/M5g need not re-encode the mapping.
3. **`rationale_blank` count.** The constructor accepts `rejected_count` 1 for `rationale_blank`
   (the table allows 1–2 for phase 3): by the precedence rule, `rationale_blank` is reported only
   when `verdict_unsupported` did not fail, so its count cannot be 2.

No specification conflict or impossibility was found.
specification's requirement that Analyst findings cite only previously validated citations more
it adds no new passage, normalization or matching behaviour.

## Unicode, trust and privacy limits

- **Segment-wise NFD is not canonical equivalence.** Canonically equivalent spellings can match
  differently. Pinned by tests: Tibetan U+0F40 U+0F74 U+0F73 and its full NFD U+0F40 U+0F71 U+0F72
  U+0F74 do not match each other in either direction; the quote U+AC00 is not found in the span
  U+AC01 but matches the first two units of the equivalent span U+1100 U+1161 U+11A8 (stored as
  U+1100 U+1161). An accepted quote is still always an exact contiguous original substring with
  exact offsets.
- **Unicode tables.** Results depend on the interpreter's `unicodedata`; a test pins Python 3.12
  and Unicode 15.0.0 (observed locally) and the maximum NFD expansion of 4 code points. Stored
  quotes are original substrings, so a table upgrade changes only future matches.
- **Trust.** Constructors and the recheck functions detect values inconsistent with the trusted
  values supplied; they do not prove which retrieval request originally ran, do not re-prove
  retrieval membership during analysis (owner and shared values must come from a trusted path that
  ran `verify_question` or `recheck_verified`), and give no protection against malicious trusted
  Python (`object.__setattr__`, `model_construct`, frame inspection) or direct database writes.
- **Privacy** covers public errors, rejections, representations and logs; explicit attribute
  access returns content by design.
- **Bounds** are the specified engineering defaults, not measured limits.

## Pending

*(Historical at implementation: implementation review, Linux verification, current-version CI and
publication have since completed; see above.)* The later slices that use these values remain
pending: M5c (safe prompt
encoding and request assembly, including any decoding of encoded quotes before matching), M5d
(persisted snapshot trust), M5e (stage persistence, reloading through the constructors and recheck
functions), M5f (the hash-covered report representation, global report bounds with no silent
truncation, and mandatory inclusion of the documentary rule finding), M5g (orchestration, repair
and job precedence) and M5h (the model adapter). Overall M5 acceptance is pending.
