# Responsible AI (v0.1)

This page states what the model does in EvidenceGuard, what a person must still decide, what has
and has not been measured, and how document data is handled.

## Purpose and limits

EvidenceGuard is **decision support** for vendor-risk reviewers. It is not legal advice, and it
does not certify compliance.

- A report organizes what the uploaded documents say, with citations, and flags conflicts and
  gaps for a human to judge.
- **Human approval does not establish that documents are authentic, and it does not certify the
  vendor as compliant.** It records that a named approver accepted one exact revision of the
  report.
- Every citation carries `authenticity: not_established`. A document labelled
  `third_party_report` is described as documentary support, never as independently verified.

## Model outputs are advisory and need human approval

Model output never leaves the system as a decision on its own:

- The model answers through two stages per question, a Verifier and a Risk Analyst
  (`packages/agents/evidenceguard_agents/data/prompts/`). Their replies are schema-validated,
  every quotation must occur in a passage retrieved for that question, and the evidence status
  is derived by code from the verdict and the cited source types, not taken from the model
  (`packages/domain/evidenceguard_domain/provenance.py`). A reply that fails these checks leaves
  the question unresolved rather than guessed.
- The review output is a draft. A reviewer records a disposition for each finding (`open`,
  `accepted` or `dismissed` with a note) in a new revision; the machine findings themselves are
  never edited (`packages/domain/evidenceguard_domain/review_report_approval.py`).
- **The approval gate:** only a user with the approver role can approve or reject, never on a
  revision they authored, and only for the exact current revision number and its SHA-256. Any
  new revision removes the effective approval. Finalizing needs an approval of the current
  revision, and only a finalized report can be exported (`POST /v1/reports/{id}/approval`,
  `/finalize` and `GET /export` in `apps/api/evidenceguard_api/reports.py`;
  [ADR-0028](decisions/0028-approval-gate-and-export.md)).
- Every export carries a fixed disclaimer that it is AI-assisted, that citations show provenance
  only, and that it is not legal advice or certification
  (`packages/agents/evidenceguard_agents/report_export.py`, `EXPORT_DISCLAIMER`).

## What the evidence labels mean

| Status | Meaning | What it does not mean |
|---|---|---|
| `vendor_claim` | Only the vendor's own statements support the answer. | That the claim is true. |
| `documentary_support` | At least one contract or third-party document supports it. | That the document is genuine or current beyond what it says. |
| `conflicting` | Current documents appear to disagree. At least two distinct quotations are cited; they may come from the same passage. | Which one is right, or that the quotations truly contradict each other. The quotation count is a structural check only. |
| `missing` | No sufficient evidence was found. Partial passages may still be cited. | That the vendor lacks the control. |

**No question is silently dropped.** Every question in a report is either answered by a finding
or listed as unresolved. A `missing` finding leaves every question it names unresolved, and a
vendor claim cannot settle a question that requires documentary support.

## Evaluation status

- No live evaluation has been run.
- No model has been chosen. `EG_REVIEW_MODEL` is set by whoever deploys it.
- There are no quality, cost or latency figures, and none should be inferred from the test
  suite. The tests use scripted providers and a mocked transport; they check contracts and
  failure handling, not answer quality.
- Prompt-injection resistance has not been measured. Document text is passed to the model as
  JSON data and the prompts tell the model to treat it as content only; that reduces the risk
  but does not remove it.

## Data handling

- The repository contains synthetic data only: fictional tenants, vendors and documents in
  `sample_data/` and in the tests. No real client, vendor or personal data belongs here.
- Uploaded document text stays in the deployer's PostgreSQL database. It is sent to a model
  provider only when a deployer enables reviews (`EG_REVIEW_PROVIDER`, `EG_REVIEW_MODEL` and a
  worker-only `EG_ANTHROPIC_API_KEY`; reviews are off by default), and then only the passages
  retrieved for each question, from the worker process.
- Logs carry fixed event names and allowlisted fields, never document text, prompts, model
  replies or keys (`packages/observability/evidenceguard_observability/jsonlog.py`).

## Limitations

- Provenance is checked, support is not: code proves that a quotation occurs in a retrieved
  passage, not that the passage supports the claim. That is the reviewer's judgment.
- Retrieval uses an offline word-hashing embedding, a lexical baseline rather than a semantic
  model, so relevant passages phrased differently from the question can be missed.
- Model refusals, timeouts and invalid output leave questions unresolved; they are not retried
  without bound.
- See [threat-model.md](threat-model.md) for security limits.
