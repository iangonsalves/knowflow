# ADR 0009: Public portfolio demo hosting

**Status:** Accepted and implemented in M8

## Context

KnowFlow is a personal portfolio project. Visitors should be able to open a public HTTPS demo and try the real authenticated application, document processing, hybrid retrieval, source evidence, and protected PDF access. Recurring hosting cost must target zero; sleep, cold starts, small quotas, and no SLA are acceptable. The approved M1–M7 architecture should remain intact.

## Decision

Host the Next.js frontend and FastAPI backend as separate Render Free web services. Use Neon for PostgreSQL with pgvector/FTS, durable processing jobs, and private S3-compatible object storage. Retain WorkOS AuthKit. Run the existing PostgreSQL-backed worker loop inside the hosted FastAPI service, sharing one ONNX E5 session with query embedding. Keep local Compose as separate web, API, worker, PostgreSQL, and MinIO services.

Do not send keep-alive traffic to defeat service sleep. The frontend shows a bounded backend startup/readiness experience. Schema changes are migrated explicitly; Render auto-deploy remains disabled and releases are manually triggered after review.

## Alternatives

- Local-only demo: rejected because portfolio visitors need a public URL.
- Paid always-on hosts: rejected for the zero-recurring-cost target.
- Run the application from the owner's computer: rejected as the primary deployment because availability would depend on personal hardware/network.
- Replace Neon/Render data paths or expose public PDF URLs: rejected because existing PostgreSQL/S3 abstractions and protected document access already fit the use case.

## Consequences

The demo is public and real, but has provider quotas, cold starts, limited compute/storage, no SLA, and one-at-a-time hosted document processing. Private PDFs stay behind KnowFlow's authorization and storage adapter. The hosted worker topology consolidates processes for memory limits without replacing durable jobs, leases, retries, or fencing. Provider terms and free-tier limits must be rechecked in the dashboards over time.
