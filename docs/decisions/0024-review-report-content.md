# ADR-0024: Review report content and deterministic Markdown

- **Status:** M5f is **reviewed, verified in CI and on main at `e7dd3be3`**, within
  its accepted scope (main publication evidence).

  commit (external review).
  passed at `3e58f650` on `feat/review-report-content`
  (feature CI evidence), and the reviewer
The specification was
Claude
  Code recovered that staged work read-only after the Codex chat response was lost, and in

  after external review findings.
- **Specification:** accepted M5f specification,
  F1–F12 and binding clarifications A/B; implementation status.
- **Preceding evidence:** M5e is reviewed, verified in CI and on main at `14f510e`, within
  [ADR-0023's recorded scope](0023-review-stage-persistence.md). Earlier Claude Code work,
  historical local results and independent external-review observations retain their attribution.

## Decision and integrity

`evidenceguard_domain.report_content` owns immutable ReportBinding, ReportVerification,
ReportStage, ReportFindingRef, ReportQuestion, ReviewReportContent, ReportMode, fixed errors
and the canonical encoder/hash/strict decoder. `evidenceguard_agents.report` owns the pure
trusted-input builder, source-bound recheck and pinned Markdown renderer. Domain imports only
the standard library and existing domain contracts; agents imports only the standard library,
domain and template values. No loader, persistence, provider, worker/API or runtime registration.

The wrapper uses `evidenceguard.review-report-content.v1` and renderer contract
`evidenceguard.review-report-markdown.v1`. M1's `evidenceguard.report-content.v1` bytes,
Unicode encoding, hash and legacy approval meanings are unchanged. The wrapper embeds the
legacy object and its separately verified digest and uses its own approval digest. It binds
tenant/review/vendor/job, request/snapshot and configuration; includes ordered planned questions,
preserved Verification status/rationale/claims/citations/authenticity, stage outcomes/reasons,
findings/follow-ups and the contract-mode stamp derived solely from hashed fields.

The builder rebuilds exact nested inputs before coercion/serialization, checks identities,
template/plan/stage order and completeness, rechecks Verification against retained evidence
and Analysis against its owner with shared=(). For every committed Verification shape it
applies M5e's E7 evidence-state rule. Closed U4 retains no evidence. Every other shape
retains evidence on the review snapshot, with `result.k` equal to the configured
`retrieval_k`, from which the stage's evidence digest is recomputed. Successful Verification survives unresolved
Analysis. The P11 documentary finding is generated deterministically even after Analysis
failure. Source request/content/evidence/dependency bindings and available pinned call settings
are checked; omitted source digests remain references, not structural proof of provenance.
The source-bound recheck rebuilds and compares canonical bytes, without enrichment.

## Validation, privacy and bounded failure

Nested exact types reject bool-as-int, subclasses, malformed questions and bypass-built nested
values before model normalization or serialization. M5c-derived distinct queries remain a
wrapper invariant; M5e itself does not independently require query uniqueness. Supplied values
do not prove genuinely pinned template origin or trusted database loading.

The codec enforces closed fields and explicit nulls, canonical UUIDs/enums/integers, nested
rebuilding, deterministic finding identities and exact P11 payload, full Analyst citation-value
equality, dependency/configuration/plan/legacy digests and unresolved projection. A lexical
scan precedes JSON parsing, enforcing ASCII, escaped-string syntax, integer spelling/magnitude,
depth/token budgets; parsing rejects duplicate keys. Canonical re-encoding equality precedes
expected wrapper-digest verification. Bare legacy and unsupported wrapper/renderer versions
are refused, never silently upgraded.

All report value repr/str methods are explicit and privacy-safe; nested content is never
delegated to a dataclass/model default representation. They expose only allowed metadata,
never titles/text, queries, quotes/evidence, rationale/claims, finding/follow-up content or
payload bytes. Explicit encoding/rendering still returns the deliberately requested content.
Ordinary errors are fresh fixed public classifications raised outside handlers, with no
original text/cause/context, warnings, output or logs. Process-control objects propagate by
identity. These are supported-input boundaries, not a hostile-process sandbox.

Limits: 200 total findings, 100 questions, existing per-question field/citation/follow-up bounds,
16,777,216 wrapper and legacy bytes, depth 16, 500,000 structural tokens, integer magnitude
2,147,483,647, and 33,554,432 Markdown bytes. Finding overflow refuses the entire report;
no truncation or dropped mandatory finding. Other caps likewise return no partial output.
These are engineering limits, not proved tight maxima or performance/quality guarantees.

## Renderer and presentation tradeoff

The pinned renderer consumes only freshly validated hash-covered content. It follows the
accepted heading/field order and emits every dynamic scalar as a labelled indented JSON
literal, with ASCII escapes and additional reversible escaping for HTML metacharacters.
Quotes round-trip exactly after one JSON decode. No string-supplied Markdown, raw HTML or
URL is emitted as active syntax in conforming CommonMark code blocks; no URL is fetched.
The tradeoff is plain literal presentation without natural prose or clickable evidence links.
No browser/CommonMark-parser test or arbitrary-viewer safety is claimed. Content integrity,
presentation handling and semantic injection resistance are separate claims.

## Implementation choices for external review

- No change to the accepted field schema, digest semantics, renderer emission order or caps
  is intended.
- Shared internal M5f boundary/preflight helpers live in the domain module and are reused
  by the agents module; they are implementation details, not additional stable public APIs.
  Existing domain constructors still perform their established semantic validation.
- The renderer checks the running ASCII byte count before storing each emitted line,
  accounting for removal of the final empty line; no partial rendering escapes on overflow.
- Existing packaging file-set/no-use assertions gain only the report.py exception needed
  for the accepted pure M5b/M5e consumer. New AST checks prohibit loaders/runtime/I/O imports
  and calls. Existing production registry assertions remain intact.
- The additive CI assertion constructs synthetic committed U4/U3 trusted values offline,
  builds/decodes/hashes/renders the wrapper and checks independently authored wire bytes and
  a literal digest. It does not execute persistence, a provider or an application review path.

## Limits and handover

No M5f control operates in an application review path; run_review is unregistered. E7 still
requires a later additive output migration and reviewed atomic output-plus-job-success writer,
replay/completeness and worker composition in M5g, never an edit to 0007. M6 must review new
wrapper revision/approval/finalization contracts and approve/export its exact digest, not a
legacy digest. U4 discarded evidence, worker obligations, the accepted M3 lease window and
open M4d trusted-snapshot limitation remain. Offline wheel checks are packaging evidence:
offline migration assertions are not PostgreSQL execution, Recall is arithmetic, Voyage is
mocked and model calls are scripted. The container smoke does not exercise M5e/M5f. No live
provider or model-quality evidence exists, and no browser/CommonMark-parser or tight
maximal-size/performance proof is claimed. No entailment, authenticity, semantic injection
resistance or live-model-quality guarantee. The accepted canary/negative-control/limitation
contract remains unchanged for the later scripted end-to-end slice; no production blacklist.
M5g–M5h and overall M5 acceptance remain pending.
