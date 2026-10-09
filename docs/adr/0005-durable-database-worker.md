# ADR 0005 PostgreSQL-backed processing jobs

**Status:** Accepted for V1

## Context

PDF extraction and embedding calls can outlast HTTP requests and must survive API restarts. V1 traffic is expected to be low and does not justify another infrastructure service.

## Decision

Use one durable PostgreSQL processing job record per document, with attempt count and last failure code. A separate worker process from the backend image claims jobs with row locking and `SKIP LOCKED`, leases work, retries transient failures with bounded backoff, and writes derived output idempotently. Do not add Redis in V1.

## Alternatives

- Process documents synchronously in API requests.
- Add Redis and a job framework immediately.
- Store an immutable row for every attempt.

## Consequences

Job creation is transactional and survives process restart. PostgreSQL polling and leases require clear timeouts, idempotency and stuck-job recovery. A queue service is a future option if measured throughput or operational needs exceed this simple design.
