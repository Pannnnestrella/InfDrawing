# Deployment interview notes

## One-minute answer

I designed a single-host production topology for InfDrawing with Nginx, Next.js, FastAPI, API/GPU/CPU workers, a one-shot migration service, PostgreSQL, Redis, and MinIO. Public traffic reaches only Nginx. The durable jobs API supports owner-scoped idempotency, PostgreSQL state, Redis dispatch, cancellation, and SSE polling. Compose health checks, persistent volumes, secret-file loading, JSON proxy logs, optional Prometheus/Grafana, smoke checks, bounded load probes, backup procedures, TLS guidance, and rollback steps are included.

The repository implements PostgreSQL job persistence, Alembic migrations, Redis/arq dispatch, API-key verification and expiration, owner-protected S3 artifacts, durable handlers for all four image operations, dependency readiness, HTTP metrics, sanitized audit logs, and provider-call metadata. The browser stores an operator-issued key in `sessionStorage`, authenticates REST calls, and receives compatibility task events through a same-origin Next.js SSE proxy. ComfyUI production packaging requires an operator-built image, audited custom nodes, compatible workflows, licensed model weights, and verified hashes.

## Why these components

PostgreSQL stores durable job state, ownership, idempotency records, artifact metadata, audit logs, and events. Redis carries arq queue coordination. MinIO stores validated uploads and generated image artifacts under server-generated keys. Separate queues reserve execution boundaries for API, CPU, and GPU work. Nginx centralizes TLS, upload limits, request IDs, and long-lived connection proxying.

## Reliability story

The API creates a PostgreSQL job before Redis dispatch. A worker acquires a lease and records state transitions. Repeated owner/idempotency-key pairs compare a canonical request hash, return the original job on a match, and return `409` on a mismatch. SSE clients resume with `after` or `Last-Event-ID`; the route polls persisted events and emits heartbeat comments. `/ready` verifies configured production dependencies, and `/metrics` exposes bounded-cardinality HTTP request metrics.

## Observability story

Nginx emits structured access logs. Application logs should include request ID, job ID, queue, stage, duration, and stable error code. Prometheus tracks request latency, job outcomes, queue depth and age, worker utilization, generation time, storage failures, and GPU memory. Alerts focus on symptoms that affect users: old queued jobs, high failure rates, unavailable workers, disk pressure, and repeated GPU OOM.

## Security story

The design keeps stateful services on an internal network and uses mounted secret files. The container entrypoint exports the exact environment fields consumed by `Settings`. API keys have indexed locators, scopes, HMAC verifiers, active flags, job ownership checks, and owner-bound event access. The current browser credential flow is scoped to one tab through `sessionStorage`. HttpOnly sessions, image pinning, vulnerability scanning, and model verification remain deployment work.

## Capacity and failure handling

GPU concurrency is configured at one job per device. Queue limits, Redis-loss reconciliation, automated retention, and disk-pressure admission control are not implemented. PostgreSQL and MinIO backup procedures are documented, and restore drills remain an operator responsibility.

## Honest implementation boundary

Implemented in this change:

- Production Compose topology, one-shot migration gate, and deploy-context Dockerfiles
- Nginx HTTP, WebSocket, SSE, request-ID, and JSON logging configuration
- Secret and environment templates without real credentials
- Optional, explicitly unconfigured ComfyUI profile
- Optional Prometheus/Grafana configuration
- Safe smoke and bounded load-probe scripts
- Deployment, API, operations, security, and rollback documentation

Pending backend integration:

- HttpOnly browser sessions for shared-device deployments
- Queue reconciliation, resource quotas, retention executor, and backup automation

Pending infrastructure validation:

- Production DNS and certificates
- NVIDIA Container Toolkit and selected GPU
- ComfyUI image, nodes, workflow versions, model licenses, and model hashes
- Image digest pinning, vulnerability scanning, host firewall, and restore drill

## Likely follow-up questions

### Why SSE and WebSocket?

SSE provides ordered durable job events, event IDs, heartbeat comments, and resume semantics. The existing WebSocket serves legacy in-process tasks with a different event shape and only last-event replay.

### How do you prevent duplicate generation?

The API binds `Idempotency-Key` to the API-key owner and a canonical request hash. Matching retries return the existing job, and changed requests return `409 Conflict`.

### What happens if Redis restarts?

PostgreSQL keeps authoritative job state, but no reconciliation process republishes jobs after Redis loss. This is a known reliability gap and a required follow-up before production traffic.

### How do you roll back a bad release?

I switch the shared image version to the previous immutable tag and recreate application services. Schema compatibility is checked before rollout. An incompatible migration uses its tested down migration or a coordinated database restore.

### Why is ComfyUI not packaged as ready to run?

Its runtime depends on GPU drivers, CUDA compatibility, custom-node code, workflow versions, licensed model weights, and large local volumes. The deployment exposes an external endpoint contract and an opt-in profile that becomes usable after those artifacts are built, scanned, and verified.
