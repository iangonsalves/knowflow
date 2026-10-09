# ADR 0004 Private object storage and deletion lifecycle

**Status:** Accepted for V1

## Context

PDF originals should not inflate relational backups or be exposed through public paths. Derived pages/chunks/vectors must be cleaned consistently when a document is removed.

## Decision

Use an object storage adapter and opaque keys. Prefer MinIO for local development if Compose remains straightforward; otherwise use a mounted volume behind the same adapter. If Azure is selected, use private Azure Blob Storage in production. On deletion, revoke access immediately, retain a tombstone while retryable cleanup runs, and purge the tombstone 7 days after successful physical cleanup. Retry cleanup for up to 24 hours before surfacing operator attention; keep access revoked.

## Alternatives

- Store PDF bytes in PostgreSQL.
- Use local filesystem only in every environment.
- Hard-delete DB records before object cleanup.

## Consequences

Storage implementation is replaceable and DB backup stays focused on structured data. Cleanup must be idempotent and observable. Seven-day post-cleanup retention is a configurable initial default and can be changed if retention obligations emerge.
