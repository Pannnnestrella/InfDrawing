# Production threat model

## Scope and assets

This model covers the single-host Compose deployment, public web/API traffic, asynchronous jobs, PostgreSQL, Redis, MinIO, workers, ComfyUI, operational logs, API keys, generated images, uploaded images, masks, prompts, and model files.

Primary assets are user content, credentials, job ownership metadata, generated artifacts, model integrity, host GPU availability, and service availability. PostgreSQL is the durable jobs and artifact-metadata system of record. Redis carries transient queue data. MinIO stores validated inputs and generated outputs under server-generated object keys.

## Trust boundaries

1. Internet clients cross the public TLS boundary at Nginx.
2. Nginx crosses the private Docker network to frontend and API.
3. API and workers cross authentication boundaries to PostgreSQL, Redis, MinIO, and ComfyUI.
4. Operators cross the host boundary through Docker, SSH, backups, and secret files.
5. Uploaded content and prompts cross from untrusted clients into parsing and model-processing components.
6. ComfyUI images, custom nodes, workflows, and model weights cross a software-supply-chain boundary.

## Principal threats and controls

### Credential theft and unauthorized API use

Bootstrap raw API keys into protected files, move them to the client secret manager, and keep only HMAC verifiers in PostgreSQL. Enforce TLS, per-key scopes, active-key revocation, and rate limits. Redact credentials from logs. Short-lived browser sessions or tickets remain a required future control.

### Broken object-level authorization

Authorize every job, event stream, upload, output, and cancellation against the authenticated owner or project. Use opaque identifiers. Signed object URLs must be short-lived and restricted to one object and method.

### Replay and duplicate execution

Require `Idempotency-Key` on mutations, bind records to principal and request digest, enforce uniqueness in PostgreSQL, and return conflicts for mismatched payloads. Workers must claim jobs atomically and make terminal transitions idempotent.

### Malicious uploads and parser exploitation

Limit request and decompressed dimensions, validate media using decoded content, reject unsupported formats, strip metadata, use random storage keys, and keep uploads outside executable paths. Run image processing as an unprivileged user with CPU, memory, time, and file-size limits. Keep Pillow, OCR, ONNX, and related native libraries patched.

### Prompt and workflow injection

Treat prompts and model output as untrusted data. Use allowlisted ComfyUI workflow templates and typed parameter substitution. Do not accept arbitrary workflow graphs, filesystem paths, node classes, shell commands, or remote URLs from clients.

### SSRF and internal service exposure

Do not provide general URL-fetch features. Allowlist required outbound hosts and schemes. Keep PostgreSQL, Redis, MinIO, Prometheus, workers, and ComfyUI off public interfaces. Validate redirects and block loopback, link-local, private, and cloud metadata destinations when user-directed fetching is introduced.

### Supply-chain compromise

Pin deployable image digests for releases, generate an SBOM, scan images, verify model hashes and licenses, and review ComfyUI custom nodes. Keep model-bearing images in a controlled registry. Rebuild base images on security updates.

### Container escape and host compromise

Run application processes as non-root, mount only required volumes, keep Docker socket out of containers, avoid privileged mode, apply resource limits, and patch the host and NVIDIA runtime. Production hardening should add read-only filesystems, dropped capabilities, seccomp/AppArmor, and explicit writable tmpfs paths after compatibility testing.

### Denial of service and GPU exhaustion

Apply body-size, request-rate, queue-depth, per-principal concurrency, image-dimension, step-count, and execution-time limits. Separate CPU and GPU queues. Reject work when queue age or free disk crosses thresholds. Preserve capacity for health checks and cancellation.

### Data leakage through artifacts, logs, and backups

Use tenant-scoped object keys, private buckets, encryption at rest where available, retention policies, and audited deletion. Avoid logging prompts or object URLs by default. Encrypt backups, restrict restore access, and test deletion propagation.

### Event-stream leakage

Authenticate SSE and WebSocket subscriptions, authorize the job before connecting and during long sessions, cap connection duration, send no secrets in URLs, and validate origin for browser sessions. Replay only events belonging to the caller.

### Database and queue tampering

Use dedicated service accounts, strong independent credentials, private networking, schema constraints, transactional job transitions, and append-only audit events for sensitive operations. Do not expose Redis administration or MinIO console publicly.

## Detection and response

Alert on authentication failures, key abuse, authorization denials, idempotency conflicts, queue age, repeated job failure, worker disappearance, GPU OOM, unusual object downloads, storage exhaustion, backup failure, and changes to deployed image digests. Correlate events using request ID, job ID, principal ID, and service.

If a key is compromised, revoke it, terminate related sessions, review affected jobs and object access, rotate dependent credentials if exposure is possible, and preserve logs. If a model or custom node is compromised, stop workers, quarantine the image and model artifacts, restore verified versions, and replay only validated jobs.

## Accepted gaps for the current repository

The backend has API-key enforcement and expiration, PostgreSQL durable jobs, Alembic migrations, Redis/arq dispatch, cancellation, persisted SSE events, owner-protected S3 artifacts, all four durable image handlers, sanitized audit data, provider-call metadata, dependency readiness, and HTTP metrics. The browser supports tab-scoped API keys and a same-origin compatibility task-event proxy. HttpOnly browser sessions, queue reconciliation, resource quotas, automated retention, and full job/worker metrics remain integration requirements. The optional managed ComfyUI profile has no supplied image or weights. A production launch review must close or explicitly accept these gaps.
