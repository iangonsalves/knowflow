# ADR 0010: Local embedding model and zero-charge AI constraint

## Context

KnowFlow needs English semantic retrieval for business policies and procedures. The portfolio must run its core document processing, embeddings and retrieval without usage-billed AI inference. The model must work on a local CPU, fit a small Docker demo, and produce vectors compatible with pgvector.

## Decision

Use the pretrained Sentence Transformers-compatible `intfloat/e5-small-v2` model locally, pinned to revision `ffb93f3bd4047442299a41ebb6fa998a38507c52`. It produces 384-dimensional English embeddings, accepts up to 512 tokens, and is MIT-licensed. Use cosine distance, normalize vectors, prefix indexed passages with `passage: ` and user searches with `query: `. Store model ID plus immutable revision, pipeline version and dimensions on `document_chunks`. Pin the V1 model revision and dimensions in settings and migration `0005`; any model change requires explicit re-embedding and a schema migration if dimensions change.

KnowFlow Portfolio Zero-Charge Constraint: the default portfolio implementation must not depend on usage-billed AI inference APIs. Core document processing, embeddings, retrieval and future Q&A must be capable of running without paid AI API calls. External paid AI providers require explicit owner approval. This does not change the approved WorkOS authentication choice.

Download model files from the pinned Hugging Face model revision on first use. Docker mounts a persistent named `model_cache` volume at `/models`, shared by API and worker. A completion marker is written only after a successful model load; subsequent API/worker loads set Sentence Transformers `local_files_only=True`. An interrupted first download is retried online and does not create the marker. Do not commit weights to Git.

## Alternatives

- OpenAI `text-embedding-3-small`: strong hosted quality and small application footprint, but requires paid usage and sends private text to a vendor; rejected by the zero-charge constraint.
- `sentence-transformers/all-MiniLM-L6-v2`: smaller (about 91 MB) and Apache-2.0, but only 256 token context and less retrieval-specific; E5 offers retrieval prefixes and 512-token context for our chunk sizes.
- Larger local models: potentially higher retrieval quality but more download, CPU and memory cost than the V1 portfolio corpus justifies.

## Consequences

The model has about 33 million parameters and the selected safetensors file is approximately 133 MB. CPU inference uses no GPU. Expect roughly 1–2 GB process memory for Python/PyTorch and loaded weights; API and worker each have their own model instance. The first download needs internet, then the named Docker cache survives `docker compose down`; `docker compose down --volumes` intentionally removes it. Input beyond 512 tokens is truncated, so chunk size and retrieval evaluation must account for model context. Model quality and CPU latency must be measured with the fixed retrieval set. The pretrained weights are open-source software; KnowFlow does not train an embedding model. Sources: [official model card and license](https://huggingface.co/intfloat/e5-small-v2) and [pinned model revision/files](https://huggingface.co/intfloat/e5-small-v2/tree/ffb93f3bd4047442299a41ebb6fa998a38507c52).
