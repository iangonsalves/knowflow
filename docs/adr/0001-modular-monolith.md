# ADR 0001 Modular monolith

**Status:** Accepted for V1

## Context

KnowFlow needs a web UI, REST API and long-running document worker. It is a small portfolio product with one developer and no demonstrated independent scaling or team ownership needs.

## Decision

Use a modular monolith: Next.js/TypeScript frontend and one Python/FastAPI backend codebase with explicit domain modules. Run the worker as a separate process from the same backend image in local development. For the constrained Render Free portfolio deployment, run the existing durable worker loop in the FastAPI process and share its ONNX embedding provider. Use PostgreSQL as system of record and pgvector for vectors.

## Alternatives

- Microservices with independently deployed APIs/workers.
- A single synchronous API process for both requests and document processing.

## Consequences

Domain boundaries remain visible without distributed-system overhead. Local API and worker can be developed and operated separately; hosted process consolidation fits the portfolio memory budget while keeping durable PostgreSQL job contracts and worker logic unchanged. Modules communicate through in-process services; a future service split requires evidence of independent scaling or ownership needs.
