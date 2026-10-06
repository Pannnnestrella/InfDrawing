# Production deployment and operations

## Status and scope

`compose.production.yaml` defines the single-host production topology. Durable jobs, migrations, storage, authentication, readiness, and metrics must pass the integration checks in this guide before the stack is treated as production-ready.

The Compose project exposes only Nginx on public ports. Grafana can bind to loopback when its profile is enabled. PostgreSQL, Redis, MinIO, frontend, Prometheus, and managed ComfyUI stay on an internal Docker network. API and workers also join a separate egress bridge for approved model providers and external ComfyUI; they publish no host ports.

## Architecture

Traffic enters `reverse-proxy`. Nginx sends browser routes to `frontend` and `/api/` traffic to `api`, including long-lived SSE and WebSocket connections. The durable jobs API records job state in PostgreSQL and enqueues work through Redis. `worker-api` consumes `agent_route`; `worker-gpu` consumes durable `txt2img`, `inpaint`, `decompose`, and `text_edit` jobs. Uploaded inputs and generated outputs use owner-protected artifact metadata with MinIO storage. The CPU queue and worker are provisioned for future CPU-only jobs.

ComfyUI defaults to an external endpoint configured by `COMFYUI_BASE_URL`. The optional `managed-comfyui` profile requires an operator-built, audited image and a mounted model directory. The repository does not distribute a ComfyUI image or model weights.

## Host prerequisites

- Docker Engine 26+ with Compose v2
- 16 GB RAM and sufficient disk for database, objects, logs, and image layers
- NVIDIA driver plus NVIDIA Container Toolkit for GPU workers
- A DNS record and TLS certificate for the production hostname
- A separately managed ComfyUI endpoint, or a tested image for the optional profile

## Configuration

`.env.production` contains non-secret deployment settings: release tag, public URL, CORS origins, database names, bucket name, provider endpoint/model/allowlist, ComfyUI endpoint, host ports, and GPU selection. Files under `deploy/secrets` contain independent database, MinIO, API-key-pepper, provider, and Grafana credentials. The application entrypoint loads secret files and constructs an escaped async PostgreSQL URL.

Set JSON list values such as `CORS_ORIGINS` and `PROVIDER_ALLOWED_HOSTS` on one line. The production provider URL must use HTTPS and its exact hostname must appear in `PROVIDER_ALLOWED_HOSTS`. Use the organization secret manager to materialize secret files during deployment and restrict host permissions.

## Bootstrap

1. Copy `.env.production.example` to `.env.production` and set `PUBLIC_BASE_URL`.
2. Create the four files listed in `deploy/secrets/README.md`. Use independent random values.
3. Place TLS files at `deploy/certs/fullchain.pem` and `deploy/certs/privkey.pem`.
4. Copy `deploy/nginx/tls.conf.example` to `deploy/nginx/conf.d/tls.conf`, then set its `server_name`.
5. Validate interpolation and build contexts:

```bash
docker compose --env-file .env.production -f compose.production.yaml config --quiet
```

6. Build immutable application images:

```bash
docker compose --env-file .env.production -f compose.production.yaml build --pull
```

7. Start the stack. The one-shot `migrate` service runs `alembic upgrade head`; API and all workers wait for its successful completion:

```bash
docker compose --env-file .env.production -f compose.production.yaml up -d
docker compose --env-file .env.production -f compose.production.yaml ps --all
```

Use one Compose project per host. Do not scale `migrate`. A failed migration keeps API and workers stopped; inspect `docker compose logs migrate`, restore or correct the migration, then rerun the one-shot service.

## API-key bootstrap and rotation

`deploy/secrets/api_key_pepper.txt` contains the HMAC pepper used to verify keys. It must contain at least 32 random characters and stay stable across API and worker restarts. It is not a client credential.

After migrations, create the first client key through a host-mounted output directory:

```bash
mkdir -p deploy/bootstrap
docker compose --env-file .env.production -f compose.production.yaml run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$PWD/deploy/bootstrap:/run/bootstrap" api \
  python scripts/bootstrap_api_key.py --name initial-admin \
  --scope agent:plan --scope generate --scope jobs:read --scope jobs:write --scope vision \
  --output-file /run/bootstrap/initial-admin.key
```

The script creates the database record, writes the raw key to a new mode-`0600` file, and never prints it. It refuses to overwrite an existing output file and removes the file if the database transaction fails. Move the file directly into the approved client secret manager, then securely delete the bootstrap copy. Do not copy it into `.env.production`, command arguments, browser storage, or logs.

PowerShell on Docker Desktop:

```powershell
New-Item -ItemType Directory -Force deploy\bootstrap | Out-Null
docker compose --env-file .env.production -f compose.production.yaml run --rm `
  --volume "${PWD}\deploy\bootstrap:/run/bootstrap" api `
  python scripts/bootstrap_api_key.py --name initial-admin `
  --scope agent:plan --scope generate --scope jobs:read --scope jobs:write `
  --scope vision --scope artifacts:read `
  --output-file /run/bootstrap/initial-admin.key
```

For rotation, create a second active key, deploy clients with the new key, verify usage, and set the old `api_keys.active` value to false through an audited database administration process. The repository has no key-revocation CLI. Authentication reads active records from PostgreSQL on every request, so key rotation requires no service restart. Keep the HMAC pepper stable; changing it invalidates every existing key.

The browser frontend accepts an operator-issued API key and stores it in `sessionStorage` for the current tab. REST calls include `X-API-Key`. Task events use a same-origin Next.js SSE proxy, which forwards the key as a server-side WebSocket handshake header. This compatibility stream is owner-bound and requires all API and WebSocket traffic for a task to reach the same backend process. The durable Jobs SSE endpoint is the production interface for programmatic clients.

## TLS

Terminate TLS at Nginx. Use TLS 1.2 or 1.3, enable HSTS after confirming HTTPS is stable, and redirect HTTP to HTTPS at the load balancer or by adding a dedicated port-80 redirect server. Renew certificates through the host certificate manager and reload Nginx:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec reverse-proxy nginx -t
docker compose --env-file .env.production -f compose.production.yaml exec reverse-proxy nginx -s reload
```

Set `BACKEND_URL` on the frontend service to the internal API address. Browser REST traffic remains same-origin, and authenticated task events pass through `/api/task-events`.

## ComfyUI modes

For an external service, set `COMFYUI_BASE_URL` to a private, reachable URL. Docker Desktop supports `host.docker.internal`. Linux Engine may require an explicit host-gateway mapping or a routable LAN address. Restrict ComfyUI at the firewall and allow only workers.

For a managed container, build and scan a ComfyUI image, mount compatible checkpoints under `COMFYUI_MODELS_DIR`, set `COMFYUI_IMAGE`, and run:

```bash
docker compose --env-file .env.production -f compose.production.yaml \
  --profile managed-comfyui up -d comfyui-gpu
```

Confirm CUDA access, custom-node versions, workflow compatibility, model licenses, hashes, and disk capacity before enabling production jobs.

## Health checks

- `/healthz`: Nginx process health
- `/health`: API liveness; no dependency calls
- `/ready`: production dependency readiness for PostgreSQL, Redis, and object storage
- `/api/v1/system/capabilities`: authenticated capability view
- Container health: `docker compose ... ps`

Run the non-destructive smoke script:

```bash
python scripts/smoke_production.py --base-url https://draw.example.com
INFDRAWING_API_KEY=... python scripts/smoke_production.py \
  --base-url https://draw.example.com
```

On Windows:

```powershell
$env:INFDRAWING_API_KEY = "temporary-key"
backend\.venv\Scripts\python.exe scripts\smoke_production.py `
  --base-url https://draw.example.com
```

## Logs and metrics

All containers write logs to stdout/stderr. Nginx emits JSON access logs with request ID, latency, upstream, and status. Application logs should emit JSON containing timestamp, level, service, request ID, job ID, queue, stage, duration, and error code. Redact API keys, prompts marked sensitive, signed URLs, and image bytes.

Enable the optional local observability profile:

```bash
docker compose --env-file .env.production -f compose.production.yaml \
  --profile observability up -d prometheus grafana
```

Grafana binds to `127.0.0.1:3001` by default. Reach it through an SSH tunnel. Prometheus scrapes API request counts and latency at `/metrics`. Job state transitions, queue depth and age, worker busy time, generation duration, GPU memory, object-store errors, and idempotency replays are the next metric families to add.

Configure Docker log rotation at the daemon level, or add per-service logging limits before sustained use.

## Backup and restore

Back up PostgreSQL and MinIO together under a maintenance window or with a recorded consistency boundary. Redis is a queue transport and should not be the system of record.

Database backup:

```bash
docker compose --env-file .env.production -f compose.production.yaml exec -T postgres \
  pg_dump -U infdrawing --format=custom infdrawing > infdrawing.dump
```

Object backup should use `mc mirror` from an operator workstation or backup container, preserving bucket version metadata when enabled. Also back up `.env.production` metadata, TLS configuration, model manifests, and secret identifiers through the organization's secret manager. Keep secret values in the approved encrypted backup system.

Test restores on an isolated Compose project. Restore PostgreSQL with `pg_restore --clean --if-exists`, restore the MinIO bucket, run migrations, then execute smoke checks. MinIO object-reference verification becomes required when generation artifacts move from local storage to the S3 adapter.

## Capacity and cleanup

Track PostgreSQL volume growth, MinIO bucket bytes and object count, Docker image usage, Prometheus retention, local application data, and ComfyUI output size. The repository has no automated retention executor. Any cleanup automation must limit deletion to terminal jobs older than the agreed period and preserve active jobs and legal holds.

Use `docker system df` for inspection. Do not schedule global `docker system prune` on a shared host. Remove only known obsolete image tags after a successful rollback window.

## Upgrade and rollback

Tag API and frontend images with the same release identifier through `INFDRAWING_VERSION`. Before upgrade, take backups, check migration reversibility, pull or build images, run migrations, and replace services. Verify readiness, one authenticated read, one test job, SSE/WS delivery, and output retrieval.

For application rollback, set `INFDRAWING_VERSION` to the previous release and run `docker compose up -d`. A database rollback requires a compatible down migration or a tested backup restore. Never run old code against a schema declared incompatible by the release notes.
