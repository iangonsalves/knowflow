# ADR 0003 Database-enforced tenant scoping

**Status:** Accepted for V1

## Context

Workspaces own documents, pages, chunks and vectors. A missed workspace filter could expose confidential documents or contaminate generated answers.

## Decision

Require membership authorization in backend services, workspace-scoped SQL in every tenant query, and composite database constraints tying dependent records to the same workspace. Search filters candidates in SQL before answer context is built. Do not implement PostgreSQL RLS in V1.

## Alternatives

- Rely on frontend filtering or opaque UUIDs.
- Add PostgreSQL row-level security in V1.

## Consequences

Authorization is explicit and covered by cross-tenant negative tests. Repository APIs must require authorized workspace context. RLS remains a future defense-in-depth option; if added later, transaction context and pool cleanup need careful design.
