# ADR 0006 Chunk and embedding storage

**Status:** Accepted for V1

## Context

V1 creates one active embedding per document chunk and searches vectors through pgvector. Additional vector history or simultaneous embedding models are not required.

## Decision

Store the vector directly on `document_chunks`, alongside embedding model/version metadata. Preserve chunk order, content hash, and inclusive page provenance. Chunking parameters are configurable and evaluated against a fixed question set.

M5 implements this with the local Sentence Transformers-compatible `intfloat/e5-small-v2`, 384 dimensions, model/version/dimension metadata and an embedded timestamp. Runtime settings must match the vector column typmod. Changing the model or dimensions requires an explicit migration and re-embedding; vectors must not be silently mixed. The M5 migration resets active READY/PROCESSING documents to UPLOADED and requeues their existing durable jobs so they become READY only after embeddings have been committed. Model selection, cache and the portfolio zero-charge constraint are recorded in ADR 0010.

## Alternatives

- Separate embeddings table keyed to chunks.
- Store vectors in an external vector database.

## Consequences

Retrieval avoids an extra join and schema remains compact. Re-embedding requires a controlled replacement/generation process. A separate table becomes justified if concurrent models, staged re-embedding or independent vector retention is needed.

M5 uses cosine distance and begins with exact pgvector scans for the small V1 corpus. Add an approximate index only after measured corpus size or latency justifies it.
