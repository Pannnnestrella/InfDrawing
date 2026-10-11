# InfDrawing local data (tracked for clone parity)

This directory holds **demo persistence** so a fresh `git clone` can restore
multi-turn edit history, the asset library, and generated/uploaded images.

| Path | Contents |
|------|----------|
| `cedit/sessions.json` | Multi-turn controlled-edit sessions + versions |
| `cedit/artifacts.json` | Artifact metadata index |
| `assets/library.json` | Asset libraries + captioned items |
| `artifacts/` | Image bytes referenced by cedit / library |
| `outputs/` | Pipeline outputs (e.g. decompose layers) |
| `uploads/` | Uploaded source images |

**Not tracked:** `logs/` (experiment dumps; regenerable).

## After cloning another machine

1. Copy `backend/.env` from the old machine (API keys are **not** in git).
2. Install deps and start backend/frontend as usual.
3. With default `auth_required=false`, data is owned by principal `development`
   and will load without setting an InfDrawing session API Key.

## What this does **not** restore

- The infinite-canvas layout (tldraw shapes live in the browser, not here).
- Browser `sessionStorage` preferences (engine / prompt style / API Key chip).
- Secrets in `.env`.
