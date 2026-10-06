# Production API usage

## Contract status

This document matches the current backend routes and models. The durable jobs API and the legacy generation API use separate execution and event paths.

## Authentication and request identity

Send the API key in `X-API-Key`. Every response should include `X-Request-ID`; clients may provide that header when correlating a request across systems. Keep keys outside source code and shell history.

`POST /api/v1/jobs` accepts `Idempotency-Key`. Generate one stable UUID for one logical operation and reuse it on retries. The uniqueness boundary is API-key owner plus idempotency key. A repeated key and matching canonical request hash return the original job. A changed payload, timeout, retry count, or kind returns `409 Conflict`.

## Browser API-key boundary

An operator creates a key with `scripts/bootstrap_api_key.py` and transfers the generated file through an approved secret-sharing channel. The user enters that key through the frontend control. The value is stored in `sessionStorage` for the current tab, and the authenticated fetch wrapper adds `X-API-Key` to REST requests.

The browser task-event client uses a fetch-based same-origin SSE stream at `/api/task-events`. The Next.js route opens the backend WebSocket and supplies `X-API-Key` in the server-side handshake. Keys are not written to `localStorage`, embedded through `NEXT_PUBLIC_*`, or placed in URLs. A short-lived HttpOnly session remains the preferred extension for shared-browser deployments.

## Job lifecycle

`POST /api/v1/jobs` creates an asynchronous job and returns `202 Accepted`:

```json
{
  "id": "1b8a65b4-fbf1-4cc8-9511-060dfa864540",
  "owner_key_id": "c7a1a31e-8a9b-4f15-b772-159148675caf",
  "kind": "agent_route",
  "payload": {"user_message": "create a watercolor lighthouse"},
  "queue": "jobs:api",
  "status": "queued",
  "attempts": 0,
  "max_attempts": 3,
  "timeout_seconds": 600,
  "cancel_requested": false,
  "result": null,
  "error": null,
  "lease_owner": null,
  "lease_expires_at": null,
  "created_at": "2026-09-02T00:00:00Z",
  "updated_at": "2026-09-02T00:00:00Z"
}
```

`JobStatus` defines `queued`, `running`, `retrying`, `succeeded`, `failed`, `cancelled`, and `dead_letter`. `GET /api/v1/jobs/{job_id}` returns an owned job. `POST /api/v1/jobs/{job_id}/cancel` requests cancellation.

`JobSubmit` contains `kind`, `payload`, `timeout_seconds`, and `max_retries`; extra fields are rejected. Public kinds are `agent_route`, `txt2img`, `inpaint`, `decompose`, and `text_edit`. `agent_route` uses `jobs:api`; image jobs use `jobs:gpu`. `txt2img` accepts prompt, sampling parameters, and `backend` (`auto`, `local`, `sd15`, `flux`, `openai`, `dashscope`). `inpaint` accepts the same `backend` field. Cloud backends require `INFD_OPENAI_API_KEY` or `INFD_DASHSCOPE_API_KEY`. The other image jobs reference owner-protected artifact IDs created through `POST /api/v1/artifacts`.

## curl examples

Create the currently implemented durable `agent_route` job:

```bash
curl --fail-with-body https://draw.example.com/api/v1/jobs \
  -H "X-API-Key: $INFDRAWING_API_KEY" \
  -H "Idempotency-Key: 86d8bb06-a099-4c27-8f84-c3edcd08e3ad" \
  -H "Content-Type: application/json" \
  -d '{"kind":"agent_route","payload":{"user_message":"create a watercolor lighthouse"}}'
```

Create a durable text-to-image job:

```bash
curl --fail-with-body https://draw.example.com/api/v1/jobs \
  -H "X-API-Key: $INFDRAWING_API_KEY" \
  -H "Idempotency-Key: 4d05ff42-d700-439f-8455-739531ea3807" \
  -H "Content-Type: application/json" \
  -d '{"kind":"txt2img","payload":{"prompt":"a small cabin at dawn","seed":42,"steps":20,"backend":"auto"}}'
```

Upload an image artifact and use its returned `id` in a durable image job:

```bash
curl --fail-with-body https://draw.example.com/api/v1/artifacts \
  -H "X-API-Key: $INFDRAWING_API_KEY" \
  -F "image=@input.png;type=image/png"

curl --fail-with-body https://draw.example.com/api/v1/jobs \
  -H "X-API-Key: $INFDRAWING_API_KEY" \
  -H "Idempotency-Key: d31bd8b1-e880-48bd-8f2b-82804ae0fd67" \
  -H "Content-Type: application/json" \
  -d '{"kind":"decompose","payload":{"image":{"artifact_id":"ARTIFACT_UUID"}}}'
```

`inpaint` requires `image.artifact_id`, `mask.artifact_id`, and `prompt`. `text_edit` requires `image.artifact_id`, a four-integer `bbox`, and `new_text`. Completed image jobs return `primary_artifact`, an `artifacts` list, and authenticated `content_url` values.

Read job state:

```bash
curl --fail-with-body https://draw.example.com/api/v1/jobs/1b8a65b4-fbf1-4cc8-9511-060dfa864540 \
  -H "X-API-Key: $INFDRAWING_API_KEY"
```

Follow Server-Sent Events after sequence 42:

```bash
curl -N "https://draw.example.com/api/v1/jobs/1b8a65b4-fbf1-4cc8-9511-060dfa864540/events?after=42" \
  -H "X-API-Key: $INFDRAWING_API_KEY"
```

## PowerShell examples

```powershell
$headers = @{
  "X-API-Key" = $env:INFDRAWING_API_KEY
  "Idempotency-Key" = [guid]::NewGuid().ToString()
}
$body = @{
  kind = "agent_route"
  payload = @{
    user_message = "create a watercolor lighthouse"
  }
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method Post `
  -Uri "https://draw.example.com/api/v1/jobs" `
  -Headers $headers -ContentType "application/json" -Body $body

Invoke-RestMethod -Method Get `
  -Uri "https://draw.example.com/api/v1/jobs/$($job.id)" `
  -Headers @{ "X-API-Key" = $env:INFDRAWING_API_KEY }
```

PowerShell 7 can stream SSE with `curl.exe -N`. Store the API key in an environment variable and pass it as a header.

## Python standard-library example

```python
import json
import os
import uuid
import urllib.request

payload = json.dumps({
    "kind": "agent_route",
    "payload": {"user_message": "create a watercolor lighthouse"},
}).encode()
request = urllib.request.Request(
    "https://draw.example.com/api/v1/jobs",
    data=payload,
    method="POST",
    headers={
        "Content-Type": "application/json",
        "X-API-Key": os.environ["INFDRAWING_API_KEY"],
        "Idempotency-Key": str(uuid.uuid4()),
    },
)
with urllib.request.urlopen(request, timeout=30) as response:
    job = json.load(response)
print(job["id"])
```

## SSE event format

The durable jobs endpoint returns frames with an increasing sequence `id`, an `event` name, and JSON `data`:

```text
id: 1
event: queued
data: {"queue":"jobs:api"}
```

Clients resume with the `after` query parameter or `Last-Event-ID` header; an explicit `after` value takes precedence. The route polls persisted events, emits heartbeat comments at the configured interval, disables proxy buffering, and closes after terminal events are drained. Native browser `EventSource` cannot set `X-API-Key`; the frontend uses a fetch-based stream client.

## WebSocket compatibility

`/api/v1/ws?task_id=...` serves only legacy in-process generation tasks. It reads `X-API-Key` during the handshake, accepts the `generate` or `jobs:read` scope, verifies task ownership, replays `task.last_event`, and consumes in-memory events until `complete`, `error`, or timeout. Unknown and foreign task IDs receive the same close code.

The browser reaches this route through the same-origin Next.js SSE proxy, which can set the handshake header on the server. This compatibility path requires one API process because `TaskState` is process-local. Durable API clients should submit through `/api/v1/jobs` and consume the PostgreSQL-backed job SSE stream.

## Errors and retries

Errors use a stable machine-readable code, human-readable message, request ID, and optional field details. Retry `429`, `502`, `503`, and `504` with exponential backoff and jitter. Honor `Retry-After`. Retry mutations with the same `Idempotency-Key`. Correct authentication, validation, conflict, and quota errors before resubmission.
