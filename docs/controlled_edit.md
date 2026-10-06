# Controlled Multi-turn Edit

Controlled Multi-turn Edit lets a user revise one image over many turns while key elements (a character's face, a weapon, a prop) stay stable. It is an independent feature with its own router, scope and page:

| Item | Value |
|---|---|
| API prefix | `/api/v1/controlled-edit` |
| Required scope | `controlled_edit` |
| Capability flag | `features.controlled_edit` (enabled when `INFD_OPENAI_API_KEY` is set) |
| Frontend page | `/` (dock on the infinite canvas; `/studio` redirects home) |
| Backend package | `backend/app/controlled_edit/` |

The protection is semantic: the system records which entities must stay fixed and enforces this through prompt constraints, reference-image anchoring and automatic VLM verification. No pixel mask is used. Every turn produces a node in a version tree, so the user can always roll back or branch.

## Concepts

**Scene entities.** When a session is created, a dedicated grounding model (Qwen-VL via DashScope when `INFD_DASHSCOPE_API_KEY` or `INFD_ALIBABA_API_KEY` is set; otherwise `INFD_CEDIT_VISION_MODEL`) parses the image into an entity tree (for example `character`, `character.face`, `character.sword`, `environment.sky`). Each entity has a dotted snake_case id, a description and a bounding box on a normalized 0–1 grid. The parser always lists `face` and `hair` for characters, because identity drift is the most visible failure. Intent parsing and verification stay on the OpenAI vision model.

**Manual box correction.** The user can drag and resize a box on `/studio`. Saving writes `bbox_source: "manual"`. On the next re-parse, only locked entities keep a manual box; other entities take the newly parsed boxes. Changing the box of a locked entity recrops its lock-time anchor.

**Region-guided edits.** Clicking an entity sets the turn target (`target_entity_ids`). Small `character.*` parts with a box use Wanx mask inpaint (white = target, black = keep). Background / whole-subject / large boxes always edit the **full current frame** with Qwen or OpenAI instruction-edit, plus optional lock paste. Locked-entity anchor crops are attached as identity references on the full-frame path.

**Entity status.** Each entity carries one of three states, stored per version node:

| Status | Prompt effect | Reference anchor | Verification |
|---|---|---|---|
| `locked` | Listed under "Preserve exactly", tied to a reference image when an anchor exists | Crop taken only for the entity the user clicked | Score below `INFD_CEDIT_PRESERVE_THRESHOLD` fails the turn |
| `approved` | Listed under "Keep unchanged unless asked" | None | Score below threshold only adds a warning |
| `editable` | No extra constraint | None | Not checked |

Locking a parent also locks every descendant (cascade). Only the clicked node gets an anchor crop; children show as locked without their own reference image and cannot be unlocked until the parent is unlocked. Unlocking the parent clears the lock on all descendants.

The preserve lists are generated deterministically from entity states; the language model never decides what to protect. An instruction that targets a locked entity (or a child of a locked entity) is rejected with HTTP 409 `lock_conflict`, and the UI offers to unlock and retry.

**Lock paste (optional).** Hard pixel paste-back of locked boxes is off by default (`INFD_CEDIT_LOCK_PASTE=false`). When enabled, only locked entities that have an anchor crop are pasted from the parent frame onto the result.

**Version tree.** Each version node stores the image artifact, the instruction, the parsed intent, the compiled prompt, the reference artifacts, an entity snapshot, the verification result, the attempt count and warnings. Editing from any node creates a child; checking out a node moves the session's current pointer without deleting history.

## Turn pipeline

1. **Intent parsing** (synchronous, inside `POST /turns`): the LLM maps the instruction and the entity table to an operation (`add`, `remove`, `replace`, `restyle`, `recolor`, `other`), target entity ids and a change description. Lock conflicts return immediately.
2. **Background run**: a pending child version is created and the turn continues as an in-process task. The frontend polls the session tree every 2 s and shows the progress step (`preparing`, `generating`, `verifying`, `parsing`).
3. **Sizing**: the source is letterboxed to the closest supported size (`1024x1024`, `1536x1024`, `1024x1536`) and restored to the original frame afterwards.
4. **Prompt compilation**: each turn may send `prompt_style` (`preserve` / `target_only`); otherwise `INFD_CEDIT_PROMPT_STYLE` is used. `preserve` includes the change, target boxes, locked/approved keep lists, framing clauses, and reference-image numbers. `target_only` describes only the change and target boxes, plus short pointers for attached identity reference crops. DashScope numbering treats the current image as last.
5. **Generation**: each turn may send `image_provider` (`dashscope` / `openai`); otherwise `INFD_CEDIT_IMAGE_PROVIDER` is used. The editor always receives the full current image plus optional lock-anchor reference crops. When `INFD_CEDIT_LOCK_PASTE` is on, anchored locked boxes are copied from the parent after generation. Transport errors are retried twice with backoff.
6. **Verification**: a subject-box framing check runs first; drift above the configured thresholds fails the attempt. Otherwise a VLM compares the before and after images, plus the anchor crops. It reports whether the change was applied, a composition score, and for each protected entity a score against the parent image and a `reference_score` against its anchor crop. The effective score of a locked entity is the lower of the two. The turn fails when the change is missing, a locked entity falls below the preserve threshold, or the composition score falls below `INFD_CEDIT_COMPOSITION_THRESHOLD`.
7. **Retry**: on failure the turn is regenerated up to `INFD_CEDIT_MAX_RETRIES` times with the failure reasons appended to the prompt. If the last attempt still fails, the image is saved and the node is marked with a warning, so the user can decide whether to keep it or roll back.
8. **Incremental re-parse**: the new image is re-parsed with the previous entity table as context. Entities keep their ids and statuses; a locked entity missing from the new parse is kept and flagged with a warning.

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/sessions` | Multipart upload (`image`, optional `title`); parses the scene and returns the tree (201) |
| `GET` | `/sessions` | List the caller's sessions |
| `GET` | `/sessions/{session_id}` | Session with all versions |
| `POST` | `/sessions/{session_id}/turns` | `{"parent_version_id", "instruction", "target_entity_ids"?, "prompt_style"?, "image_provider"?}`; returns the pending version (202) or 409 `lock_conflict` / editor unavailable |
| `POST` | `/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/status` | Set `locked` / `approved` / `editable`; locking stores an anchor crop |
| `PUT` | `/sessions/{session_id}/versions/{version_id}/entities/{entity_id}/bbox` | Save a manual box `{x, y, w, h}` in normalized image units |
| `POST` | `/sessions/{session_id}/checkout` | Move the current pointer to a version |
| `DELETE` | `/sessions/{session_id}/versions/{version_id}` | Delete a version and all descendants (not the root; not while pending/running). Cursor moves to the parent when needed. Image artifacts on disk are kept. |
| `GET` | `/artifacts/{artifact_id}` | Image bytes, restricted to the session owner |

Errors use the standard error envelope. Upstream model failures map to 502, missing resources to 404, and edits from a version that is still running to 409.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `INFD_CEDIT_IMAGE_PROVIDER` | `dashscope` | Image editor: `dashscope` (`qwen-image-edit-plus`) or `openai` |
| `INFD_CEDIT_IMAGE_MODEL` | `qwen-image-edit-plus` | DashScope edit model when the provider is `dashscope` |
| `INFD_CEDIT_VISION_MODEL` | `gpt-4o` | Vision model for intent parsing and verification |
| `INFD_CEDIT_SCENE_PROVIDER` | `dashscope` | Scene-parsing provider; set to `openai` to reuse the vision model |
| `INFD_CEDIT_SCENE_MODEL` | `qwen3-vl-plus` | Dedicated grounding model (DashScope compatible mode) |
| `INFD_CEDIT_SCENE_BASE_URL` | DashScope compatible-mode `/v1` | OpenAI-compatible chat completions endpoint |
| `INFD_CEDIT_SCENE_BBOX_FORMAT` | `xyxy_1000` | How `box_2d` is read: `xyxy_1000`, `yxyx_1000`, or `xyxy_pixel` |
| `INFD_CEDIT_VISION_TIMEOUT_SECONDS` | `90` | Timeout per vision call |
| `INFD_CEDIT_PRESERVE_THRESHOLD` | `0.7` | Minimum score for locked entities |
| `INFD_CEDIT_COMPOSITION_THRESHOLD` | `0.75` | Minimum composition score |
| `INFD_CEDIT_MAX_RETRIES` | `1` | Automatic regenerations after a failed verification |
| `INFD_CEDIT_MAX_REFERENCE_IMAGES` | `4` | Maximum anchor crops attached per turn |
| `INFD_CEDIT_INPUT_FIDELITY` | `high` | `input_fidelity` sent to the OpenAI image model |
| `INFD_CEDIT_MAX_ENTITIES` | `30` | Upper bound on parsed entities |
| `INFD_CEDIT_PROMPT_STYLE` | `preserve` | Default edit prompt style when the Studio picker does not override: `preserve` or `target_only` |
| `INFD_CEDIT_LOCK_PASTE` | `false` | When true, paste anchored locked boxes from the parent onto each result |
| `INFD_CEDIT_LOCK_FEATHER` | `0.12` | Feather width when pasting locked or cropped boxes |
| `INFD_CEDIT_SUBJECT_SHIFT_THRESHOLD` | `0.08` | Subject-center shift that fails framing before VLM review |
| `INFD_CEDIT_SUBJECT_AREA_THRESHOLD` | `0.15` | Subject-area change that fails framing before VLM review |

Sessions and versions are stored in `edit_sessions` / `edit_versions` (migration `0002_controlled_edit`) when a database is configured. In local `memory` mode they are written to `data/cedit/sessions.json` after every create or save, and artifact metadata is written to `data/cedit/artifacts.json`, so a backend restart keeps the version tree.

## End-to-end check

`scripts/cedit_e2e.py` creates a session against a running backend, locks the face, sword and shield, runs three turns (witch hat, Halloween night background, glowing pumpkin) and writes images, scores and the configuration to `data/logs/{YYYYMMDD}_controlled_edit_e2e/`:

```bash
backend/.venv/Scripts/python scripts/cedit_e2e.py --image path/to/source.png --out data/logs/<run_dir>
```

## Known limitations

- The VLM verifier is lenient: in the 2026-10-05 runs it scored composition 1.0 on a turn with a visible push-in, and it does not detect gradual brushwork degradation across turns. Framing drift now fails those zoom-in cases before the VLM call.
- Grounding uses Qwen-VL (`qwen3-vl-plus` by default). Boxes are tight enough for face, sword and shield on the 2026-10-05 comparison set; group boxes (character, environment) still cover extra background. A comparison script lives at `scripts/cedit_grounding_compare.py`.
- Each turn re-encodes the full image, so texture quality can degrade over long chains. Branching from an earlier node is the recovery path.
- Turns run inside the API process; a restart interrupts running turns. Session trees and artifact metadata persist in `data/cedit/` in local `memory` mode.
