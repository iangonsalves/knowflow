# KnowFlow

KnowFlow is a multi-tenant document knowledge platform for organizing business documents and finding source-backed evidence in them. Workspace members can upload text-based PDFs, group them into Knowledge Areas, and ask questions in natural language. KnowFlow searches the documents and presents relevant passages with document and page citations so people can check the original source.

## What it does

- Workspaces with **Owner** and **Member** roles
- Knowledge Areas for organizing documents
- Private PDF upload, processing, viewing, and deletion
- Page-aware text extraction and deterministic chunking
- **Ask KnowFlow** with best, supporting, or potentially related evidence
- Protected source links that open the original document at the cited page
- Workspace-scoped access control and tenant isolation

KnowFlow V1 does **not** use a generative LLM and does not write or paraphrase answers. Ask KnowFlow retrieves and displays verbatim evidence from authorized source documents. Local open-source embeddings power semantic search; no paid AI API or API key is required.

## How search works

Uploaded passages are embedded locally with `intfloat/e5-small-v2` and indexed in PostgreSQL with pgvector. A question is searched using both PostgreSQL full-text search and vector similarity. Reciprocal Rank Fusion combines the ranked results, then KnowFlow applies deterministic evidence-quality checks and shows the selected passages with provenance.

## Technologies

| Technology | Use in KnowFlow |
| --- | --- |
| Next.js, React, TypeScript | Responsive web application and server-side backend-for-frontend (BFF) |
| WorkOS AuthKit | Sign-in and identity; KnowFlow workspace membership remains the authorization source |
| FastAPI, Python 3.12 | API, authorization, document operations, search, and Ask endpoints |
| PostgreSQL, SQLAlchemy, Alembic | Application data, tenant constraints, durable processing jobs, and schema migrations |
| pgvector and PostgreSQL full-text search | Semantic and lexical retrieval combined with Reciprocal Rank Fusion |
| `intfloat/e5-small-v2` | Local CPU embeddings with 384-dimensional vectors; no inference service |
| ONNX Runtime (deployment option) | CPU-only INT8 E5 inference for the constrained deployment image; local development retains Sentence Transformers/PyTorch |
| pypdf | Text extraction and page provenance for selectable-text PDFs; OCR is not included |
| S3-compatible object storage | Private PDF storage; MinIO locally and configured cloud-compatible storage for hosted use |
| PostgreSQL-backed Python worker | Durable document processing with leases, retries, and recovery |
| Docker Compose | Local web, API, worker, PostgreSQL, and MinIO environment |
| GitHub Actions | Automated repository checks |

## Local development

The repository includes a Docker Compose setup for running KnowFlow locally. Start with the [Engineering Guide](docs/KNOWFLOW_ENGINEERING_GUIDE.md) for prerequisites, WorkOS setup, environment configuration, and verification commands.

```sh
cp .env.example .env
docker compose up --build -d
docker compose run --rm api alembic upgrade head
```

The local web app is available at <http://localhost:3000>; the FastAPI docs are at <http://localhost:8000/docs>. The first local embedding-model download requires internet access; subsequent starts use the persistent model cache.
