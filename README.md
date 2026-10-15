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

**[Open the live demo](https://knowflow-web.onrender.com)** — the Render Free service may need time to wake after inactivity.

## How document processing and Ask work

An uploaded PDF is stored privately and recorded with a durable PostgreSQL processing job. The worker extracts selectable text page by page, makes deterministic page-aware chunks, and embeds each chunk locally. Once processing completes, the document is searchable.

For Ask KnowFlow, the question is embedded locally and searched with both PostgreSQL full-text search and pgvector cosine similarity. Reciprocal Rank Fusion combines the ranked results. A deterministic M6 evidence layer selects source passages, removes duplicates, and retains document/page provenance. KnowFlow displays the evidence; it does not compose an answer.

## Architecture

| Local development | Hosted portfolio demo |
| --- | --- |
| Next.js, FastAPI, and a separate Python worker in Docker Compose | Next.js and FastAPI as separate Render Free web services; the durable worker loop runs inside the FastAPI service |
| PostgreSQL 16 with pgvector; MinIO for private PDFs | Neon PostgreSQL with pgvector and FTS; Neon private object storage |
| CPU Sentence Transformers/PyTorch E5 provider, cached in a Docker volume | CPU ONNX Runtime with the pinned INT8 E5-small-v2 artifact baked into the backend image |

Both topologies use WorkOS AuthKit for authentication and KnowFlow workspace memberships for authorization. Hosted process consolidation shares one ONNX session between Ask and the durable PostgreSQL worker; it does not replace jobs with in-memory background tasks. Hosted processing handles one document at a time with embedding batch size 1. The hosted model uses the same E5 revision and 384 dimensions, with separate embedding-version metadata; vectors from the two provider versions must not be mixed without re-embedding.

The public portfolio deployment uses free tiers and can sleep when idle. A cold request may wait while the backend starts. See the [Engineering Guide](docs/KNOWFLOW_ENGINEERING_GUIDE.md) for environment-variable names, migrations, health checks, deployment maintenance, and the live-demo smoke checklist. Secrets are configured in provider dashboards and are not stored in this repository.

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

## Tests and limitations

The backend suite covers API authorization, processing, embeddings, evidence selection, and PostgreSQL retrieval/job behavior. The frontend has Node helper tests plus lint, typecheck, and production-build checks. PostgreSQL-specific tests require PostgreSQL with pgvector; SQLite does not validate FTS, vector operators, or `SKIP LOCKED` behavior.

V1 supports selectable-text PDFs only (no OCR), has no persisted Ask conversation history, and presents evidence rather than generated summaries. Evidence selection is deterministic and can be ambiguous when a retrieved chunk contains multiple related facts. Render Free may cold-start and the hosted worker processes one job at a time. The system is a portfolio demo without a production SLA.
