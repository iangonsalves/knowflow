# ADR 0003 Database-enforced tenant scoping

**Status:** Accepted for V1

## Context

Workspaces own documents, pages, chunks and vectors. A missed workspace filter could expose confidential document evidence.

## Decision

Require membership authorization in backend services, workspace-scoped SQL in every tenant query, and composite database constraints tying dependent records to the same workspace. Search filters candidates in SQL before answer context is built. Do not implement PostgreSQL RLS in V1. In M2, workspace reads first resolve `(user_id, workspace_id)` membership, then execute queries constrained to that workspace; inaccessible workspace IDs return 404. Owner policy is a centralized backend check.

## Alternatives

- Rely on frontend filtering or opaque UUIDs.
- Add PostgreSQL row-level security in V1.

## Consequences

Authorization is explicit and covered by cross-tenant negative tests. Repository APIs must require authorized workspace context. Role values are constrained to `OWNER` and `MEMBER`; Owner removal/demotion is serialized per workspace and the final Owner is protected by a transactional service rule. RLS remains a future defense-in-depth option; if added later, transaction context and pool cleanup need careful design.
