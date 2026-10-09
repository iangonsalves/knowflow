# ADR 0001 Modular monolith

**Status:** Accepted for V1

## Context

KnowFlow needs a web UI, REST API and long-running document worker. It is a small portfolio product with one developer and no demonstrated independent scaling or team ownership needs.

## Decision

Use a modular monolith: Next.js/TypeScript frontend and one Python/FastAPI backend codebase with explicit domain modules. Run the worker as a separate process from the same backend image. Use PostgreSQL as system of record and pgvector for vectors.

## Alternatives

- Microservices with independently deployed APIs/workers.
- A single synchronous API process for both requests and document processing.

## Consequences

Domain boundaries remain visible without distributed-system overhead. API and worker can scale as separate processes later. Modules communicate through in-process services; durable DB contracts connect API and worker. A future service split requires evidence of independent scaling or ownership needs.
