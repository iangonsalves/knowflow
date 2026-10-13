# ADR 0011: Evidence-based Q&A without generative LLM inference

**Status:** Accepted for V1

## Context

KnowFlow is a personal portfolio project that must run its core product without usage-billed AI APIs and on constrained/free hosting. M5 already provides local semantic embeddings, PostgreSQL full-text search, pgvector and RRF. A generative model would add model/API cost, memory and operational needs, while making unsupported paraphrases harder to rule out.

## Decision

V1 Ask KnowFlow uses hybrid retrieval and returns selected verbatim source passages. Retrieval similarity can surface question/reference text or weak matches, so M6 needs a deterministic evidence-quality step before presenting the best passage. It must preserve source provenance, avoid duplicate evidence, and communicate unsupported questions safely. It does not synthesize or paraphrase an answer. Source navigation uses the existing authorized document route.

The evidence selector prefers substantive declarative text and discounts interrogative/reference-only passages. M5 provides lexical rank and actual pgvector cosine similarity internally. M6 may accept a high-similarity candidate when it contains the requested answer type (frequency, quantity, timing, or responsible role), or use adequate lexical overlap with FTS support. Query concept coverage remains a false-positive safeguard, but it is not a binary requirement for every concept: semantic paraphrases must be supported by a sufficiently similar E5 candidate and answer-bearing source structure. A growing business-domain synonym dictionary is deliberately not used. M5 rank/RRF alone never proves relevance. Partial matches are displayed separately as weak related passages, and no-evidence results show no evidence cards. Extracted text is deduplicated by normalized text and near-overlap, including across best/supporting selections. These labels and cosine thresholds are heuristic signals, not probabilities or proof that a passage answers the question. RRF scores are not displayed as confidence.

## Alternatives

- Hosted generative LLM API: rejected because it may charge per use and sends document/query content to a provider.
- Local generative model: rejected for V1 because of model size and hosting/RAM requirements.
- Search-only results: retained internally as the M5 retrieval API but not chosen for the user-facing Ask flow because raw ranked chunks need clearer evidence grouping and source presentation.

## Consequences

- No LLM API key, generative inference service, per-question AI charge or multi-GB model is required.
- Users can inspect the original evidence directly; generated-answer hallucination is eliminated from V1.
- The product does not summarize or synthesize answers; users interpret the passages themselves.
- Passage selection and deduplication are deterministic and testable but can sometimes retain a full chunk when isolation is uncertain. Heuristic quality thresholds can miss valid paraphrased evidence or retain weak related text, so acceptance queries must cover both supported and unsupported questions.
- A generation adapter may be considered only in a future scope discussion; it is not part of V1 and is not implemented.
