# ADR 0005 PostgreSQL-backed processing jobs

**Status:** Accepted for V1

## Context

PDF extraction and embedding calls can outlast HTTP requests and must survive API restarts. V1 traffic is expected to be low and does not justify another infrastructure service.

## Decision

Use one durable PostgreSQL processing job record per document, with attempt count and last failure code. The worker loop claims jobs with row locking and `SKIP LOCKED`, leases work, retries transient failures with bounded backoff, and writes derived output idempotently. Local development runs it as a separate process from the backend image. The constrained hosted portfolio service runs the same loop inside FastAPI, one document at a time, sharing the configured ONNX embedding provider. Do not add Redis in V1, including solely for single-instance rate limiting. Revisit rate-limit enforcement only if deployment becomes multi-instance.

## Alternatives

- Process documents synchronously in API requests.
- Add Redis and a job framework immediately.
- Store an immutable row for every attempt.

## Consequences

Job creation is transactional and survives process restart. PostgreSQL polling and leases require clear timeouts, idempotency and stuck-job recovery. A queue service is a future option if measured throughput or operational needs exceed this simple design.
