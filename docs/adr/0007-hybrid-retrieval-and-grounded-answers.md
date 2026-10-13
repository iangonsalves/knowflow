# ADR 0007 Hybrid retrieval

**Status:** Accepted for V1

## Context

Exact policy terms and numbers benefit from keyword matching, while paraphrases benefit from semantic retrieval. Both result sets need to be fused and source provenance must be verifiable.

## Decision

Use PostgreSQL full-text search plus pgvector semantic search, both scoped to authorized READY documents. Combine independent candidate ranks using reciprocal-rank fusion (1-based rank, `1 / (rrf_k + rank)`, default `rrf_k=60`). Candidate counts and result limits are configurable. M5 returns source passages, filename/page provenance, hybrid score and component ranks. M6 selects and presents evidence from these results without generating or paraphrasing answers. See ADR 0011. The M5 local embedding model is the only model inference in V1 and remains covered by ADR 0010's zero-charge constraint.

## Alternatives

- Keyword-only retrieval.
- Vector-only retrieval.
- Weighted score fusion without normalized score calibration.
- Separate search/vector infrastructure in V1.
- Raw score blending: lexical rank and cosine distance have different scales and should not be added directly.

## Consequences

One relational platform supports exact and semantic retrieval. Current M5 defaults are 30 lexical candidates, 30 vector candidates and 6 final results; evaluation must track evidence recall and ranking quality. RRF scores are rankings, not calibrated confidence probabilities. Authorization and source metadata come from server-owned rows.
