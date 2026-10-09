# ADR 0006 Chunk and embedding storage

**Status:** Accepted for V1

## Context

V1 creates one active embedding per document chunk and searches vectors through pgvector. Additional vector history or simultaneous embedding models are not required.

## Decision

Store the vector directly on `document_chunks`, alongside embedding model/version metadata. Preserve chunk order, content hash, and inclusive page provenance. Chunking parameters are configurable and evaluated against a fixed question set.

## Alternatives

- Separate embeddings table keyed to chunks.
- Store vectors in an external vector database.

## Consequences

Retrieval avoids an extra join and schema remains compact. Re-embedding requires a controlled replacement/generation process. A separate table becomes justified if concurrent models, staged re-embedding or independent vector retention is needed.
