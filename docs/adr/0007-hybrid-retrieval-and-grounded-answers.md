# ADR 0007 Hybrid retrieval and grounded answers

**Status:** Accepted for V1

## Context

Exact policy terms and numbers benefit from keyword matching, while paraphrases benefit from semantic retrieval. Both result sets need to be fused and citations must be verifiable.

## Decision

Use PostgreSQL full-text search plus pgvector semantic search, both scoped to authorized READY documents. Combine independent candidate ranks using reciprocal-rank fusion (1-based rank, `1 / (rrf_k + rank)`, default `rrf_k=60`). Candidate counts and result limits are configurable. M5 returns source passages, filename/page provenance, hybrid score and component ranks. LLM generation, answer citations and insufficient-evidence decisions remain M6. M6 must follow the KnowFlow Portfolio Zero-Charge Constraint in ADR 0010; no paid inference API is assumed or permitted without explicit owner approval.

## Alternatives

- Keyword-only retrieval.
- Vector-only retrieval.
- Weighted score fusion without normalized score calibration.
- Separate search/vector infrastructure in V1.
- Raw score blending: lexical rank and cosine distance have different scales and should not be added directly.

## Consequences

One relational platform supports exact and semantic retrieval. Current M5 defaults are 30 lexical candidates, 30 vector candidates and 6 final results; evaluation must track evidence recall and ranking quality. LLM output is never authoritative for tenant access or source metadata. Prompt injection is mitigated by scoped retrieval and constrained model capability, not prompts alone.
