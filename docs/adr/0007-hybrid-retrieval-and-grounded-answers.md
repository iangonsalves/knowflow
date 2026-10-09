# ADR 0007 Hybrid retrieval and grounded answers

**Status:** Accepted for V1

## Context

Exact policy terms and numbers benefit from keyword matching, while paraphrases benefit from semantic retrieval. Both result sets need to be fused and citations must be verifiable.

## Decision

Use PostgreSQL full-text search plus pgvector semantic search, both scoped to authorized READY documents. Combine candidate ranks using reciprocal-rank fusion. Bound context, instruct the LLM to use retrieved passages as evidence, validate structured citation IDs against retrieved rows, and return an insufficient-evidence status when support is inadequate.

## Alternatives

- Keyword-only retrieval.
- Vector-only retrieval.
- Weighted score fusion without normalized score calibration.
- Separate search/vector infrastructure in V1.

## Consequences

One relational platform supports exact and semantic retrieval. Evaluation must track evidence recall and abstention behavior; rank fusion still needs tuning. LLM output is never authoritative for tenant access or source metadata. Prompt injection is mitigated by scoped retrieval and constrained model capability, not prompts alone.
